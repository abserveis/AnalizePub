"""
EPUBAnalyzer: parses an EPUB file and detects all accessibility issues.
Works with EPUB 2.0.1 and EPUB 3.x.
"""

import zipfile
import os
import re
import uuid
from pathlib import Path, PurePosixPath
from typing import List, Optional, Tuple, Dict
from lxml import etree

from .constants import NS, EPUB_TYPE_TO_ARIA, DECORATIVE_IMAGE_PATTERNS, REQUIRED_A11Y_METADATA, GENERIC_ALT_TEXTS
from .models import Issue, ImageItem, TableItem, LangItem, AnalysisReport
from .fixes.contrast import analyse_css_text
from .fixes.metadata import normalize_dc_date


class EPUBAnalyzer:
    """
    Analyzes an EPUB file for accessibility issues.
    Usage:
        analyzer = EPUBAnalyzer('path/to/book.epub')
        report = analyzer.analyze()
    """

    def __init__(self, epub_path: str):
        self.epub_path = epub_path
        self.zip = zipfile.ZipFile(epub_path, 'r')
        self.opf_path: Optional[str] = None
        self.opf_root: Optional[etree._Element] = None
        self.epub_version: str = 'unknown'
        self.language: str = 'und'
        self.title: str = 'Unknown'
        self.manifest: Dict[str, Dict] = {}   # id -> {href, media-type, ...}
        self.spine_idrefs: List[str] = []
        self.issues: List[Issue] = []
        self.images_for_review: List[ImageItem] = []
        self.tables_for_review: List[TableItem] = []
        self.lang_items: List[LangItem] = []
        self._issue_counter = 0
        self.has_page_list: bool = False    # <nav epub:type="page-list"> found in nav doc
        self.has_page_source: bool = False  # OPF already declares pageBreakSource

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def analyze(self) -> AnalysisReport:
        """Run full analysis and return an AnalysisReport."""
        self._parse_container()
        self._parse_opf()
        self._analyze_opf_metadata()
        self._analyze_documents()
        self._analyze_page_list()

        self._analyze_ncx_uid()
        self._analyze_css_files()
        self._analyze_inline_styles()
        self._analyze_inline_lang()

        return AnalysisReport(
            epub_path=self.epub_path,
            epub_version=self.epub_version,
            title=self.title,
            language=self.language,
            total_documents=len(self.spine_idrefs),
            total_images=len(self.images_for_review),
            issues=self.issues,
            images_for_review=self.images_for_review,
            tables_for_review=self.tables_for_review,
            lang_items=self.lang_items,
            auto_fix_count=sum(1 for i in self.issues if i.auto_fixable),
            manual_review_count=len(self.images_for_review) +
                                len(self.tables_for_review) +
                                len(self.lang_items) +
                                sum(1 for i in self.issues if not i.auto_fixable),
            has_page_list=self.has_page_list,
            has_page_source=self.has_page_source,
        )

    # ------------------------------------------------------------------ #
    #  Container & OPF parsing
    # ------------------------------------------------------------------ #

    def _parse_container(self):
        """Read META-INF/container.xml to find the OPF path."""
        container_xml = self.zip.read('META-INF/container.xml')
        root = etree.fromstring(container_xml)
        rootfile = root.find(
            './/{urn:oasis:names:tc:opendocument:xmlns:container}rootfile'
        )
        if rootfile is None:
            raise ValueError("Cannot find rootfile in container.xml")
        self.opf_path = rootfile.get('full-path')

    def _parse_opf(self):
        """Parse the OPF package document."""
        opf_data = self.zip.read(self.opf_path)
        self.opf_root = etree.fromstring(opf_data)

        # Version
        self.epub_version = self.opf_root.get('version', '2.0')

        # Title
        dc_title = self.opf_root.find('.//{http://purl.org/dc/elements/1.1/}title')
        if dc_title is not None and dc_title.text:
            self.title = dc_title.text.strip()

        # Manifest
        manifest_el = self.opf_root.find('{http://www.idpf.org/2007/opf}manifest')
        if manifest_el is not None:
            for item in manifest_el.findall('{http://www.idpf.org/2007/opf}item'):
                item_id = item.get('id')
                self.manifest[item_id] = {
                    'href': item.get('href'),
                    'media-type': item.get('media-type', ''),
                    'properties': item.get('properties', ''),
                }

        # Spine
        spine_el = self.opf_root.find('{http://www.idpf.org/2007/opf}spine')
        if spine_el is not None:
            for itemref in spine_el.findall('{http://www.idpf.org/2007/opf}itemref'):
                idref = itemref.get('idref')
                if idref:
                    self.spine_idrefs.append(idref)

        # Language — collected AFTER manifest+spine so _detect_primary_language
        # can sample spine documents to resolve ambiguous multi-language OPFs.
        dc_langs = self.opf_root.findall('.//{http://purl.org/dc/elements/1.1/}language')
        lang_values = [el.text.strip() for el in dc_langs if el.text and el.text.strip()]
        if lang_values:
            if len(lang_values) == 1:
                self.language = lang_values[0]
                # Verify the declared language against the actual content.
                # It is common for editors to export with a wrong language tag
                # (e.g. 'en' when the book is in Spanish).
                self._check_language_match()
            else:
                # Multiple dc:language values — common in InDesign exports where
                # paragraph/character styles carry stray language assignments.
                # Sample spine documents to find the most frequent xml:lang value
                # and use that as the primary language.
                # Falls back to candidates[0] if no content hint is found.
                self.language = self._detect_primary_language(lang_values)

    def _check_language_match(self) -> None:
        """
        Sample up to 10 spine documents and compare their actual content language
        against the single declared dc:language.  Three detection passes, in order
        of confidence:

          1. xml:lang / lang on <html> element (most authoritative)
          2. xml:lang on any element in the document (InDesign EPUB2 pattern)
          3. Word-frequency heuristic for Spanish vs English as a last resort
             when no markup language hints are present at all

        If the most confidently detected language differs from the declared one,
        an issue is created so the user is prompted to correct it on the report page.
        Only called when exactly one dc:language value is declared in the OPF.
        """
        from collections import Counter
        import re as _re

        opf_dir  = self.opf_path.rsplit('/', 1)[0] if '/' in self.opf_path else ''
        xhtml_ns = 'http://www.w3.org/1999/xhtml'
        xml_ns   = 'http://www.w3.org/XML/1998/namespace'

        html_lang_counter:  Counter = Counter()   # Pass 1: <html> lang
        elem_lang_counter:  Counter = Counter()   # Pass 2: any element xml:lang
        sampled_texts: list = []                  # Pass 3: raw text
        checked = 0

        # Use a strict parser that disables DTD loading and attribute defaults.
        # EPUB2 XHTML files often have DOCTYPEs like:
        #   <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "…">
        # libxml2's default parser may load the DTD from its internal catalog
        # and inject attribute defaults (e.g. xml:lang="en" from the public
        # identifier's language code), causing false language-mismatch alerts.
        _safe_parser = etree.XMLParser(
            load_dtd=False,
            no_network=True,
            attribute_defaults=False,
            recover=True,
            remove_blank_text=False,
        )

        for idref in (self.spine_idrefs or []):
            item = self.manifest.get(idref, {})
            href = item.get('href', '')
            if not href:
                continue
            abs_href = f'{opf_dir}/{href}' if opf_dir else href
            try:
                data = self.zip.read(abs_href)
                doc  = etree.fromstring(data, _safe_parser)

                # Pass 1 — <html> element
                html_el = (doc if (doc.tag == f'{{{xhtml_ns}}}html' or doc.tag == 'html')
                           else doc.find(f'{{{xhtml_ns}}}html') or doc.find('html'))
                if html_el is not None:
                    lang = (html_el.get(f'{{{xml_ns}}}lang') or
                            html_el.get('lang') or '').strip()
                    if lang:
                        html_lang_counter[lang] += 1

                # Pass 2 — any element with xml:lang (EPUB2 InDesign pattern)
                for el in doc.iter():
                    if not isinstance(el.tag, str):
                        continue
                    lang = (el.get(f'{{{xml_ns}}}lang') or '').strip()
                    if lang:
                        elem_lang_counter[lang] += 1

                # Pass 3 — collect text for word-frequency fallback
                texts = [t for t in doc.itertext() if t and t.strip()]
                sampled_texts.append(' '.join(texts[:200]))

            except Exception:
                pass
            checked += 1
            if checked >= 10:
                break

        def _base(tag: str) -> str:
            return tag.lower().split('-')[0]

        declared_lang = (self.language or '').lower()
        detected_lang: str = ''
        method: str = ''

        # --- Pass 1: <html> lang attribute (most authoritative) ---
        if html_lang_counter:
            top = html_lang_counter.most_common(1)[0][0]
            if _base(top) != _base(declared_lang):
                detected_lang = top
                method = 'html-lang'

        # --- Pass 2: element-level xml:lang (InDesign EPUB2 pattern) ---
        # Only used when pass 1 found no mismatch AND the most frequent element
        # lang differs from the declared one.  If it matches, we fall through to
        # the word-frequency check to guard against wrongly-tagged documents.
        if not detected_lang and elem_lang_counter:
            top = elem_lang_counter.most_common(1)[0][0]
            if _base(top) != _base(declared_lang):
                detected_lang = top
                method = 'element-lang'

        # --- Pass 3: word-frequency heuristic (always runs as cross-check) ---
        # Runs when passes 1/2 found no markup mismatch OR when there are no
        # lang attributes at all.  Needed for EPUB2 files where the tool itself
        # may have applied the wrong language tag on the first pass.
        #
        # Only active for the three languages we have reliable word sets for.
        # For other languages (fr, de, pt, …) word-frequency is skipped to
        # avoid false positives — markup-based passes are sufficient there.
        if not detected_lang and sampled_texts and _base(declared_lang) in ('es', 'en', 'ca'):
            # Words DISTINCTIVE to Spanish — NOT shared with Catalan.
            # Excluded CA-shared words: de, la, que, el, en, y, los, del, las,
            # por, un, con, una, es, se, no, son, al, lo, ser, han, sobre, ya
            _ES = {
                'también', 'más', 'pero', 'para', 'como', 'muy', 'hay',
                'esto', 'esta', 'están', 'fue', 'había', 'tiene', 'sin',
                'así', 'sus', 'cuando', 'donde', 'siempre', 'después',
                'mismo', 'puede', 'hacer', 'tener', 'todo', 'todos',
                'otros', 'porque', 'entre', 'desde', 'hasta', 'ellos',
                'ellas', 'nosotros', 'vosotros', 'usted', 'ustedes',
                'ese', 'esa', 'esos', 'esas', 'aquel', 'aquella',
            }
            # Words distinctive to English.
            _EN = {
                'the', 'and', 'is', 'was', 'has', 'are', 'be', 'or',
                'at', 'from', 'but', 'not', 'they', 'their', 'were',
                'have', 'had', 'this', 'that', 'with', 'for', 'an',
                'will', 'would', 'can', 'could', 'should', 'been',
                'its', 'of', 'as', 'by', 'we', 'our', 'which', 'he',
                'she', 'it', 'do', 'did', 'if', 'so', 'what', 'when',
            }
            # Words distinctive to Catalan — NOT shared with Spanish.
            _CA = {
                'però', 'per', 'amb', 'molt', 'els', 'unes', 'uns',
                'quan', 'alguns', 'algunes', 'també', 'sempre', 'abans',
                'després', 'tots', 'totes', 'altre', 'altres', 'fer',
                'pot', 'és', 'són', 'perquè', 'aquest', 'aquesta',
                'aquells', 'aquelles', 'als', 'dels', 'cal', 'només',
                'encara', 'ara', 'tot', 'tota', 'havia', 'tenen',
                'nosaltres', 'vosaltres', 'ell', 'ella', 'ells', 'elles',
            }
            # Include Catalan characters in the tokeniser.
            combined = ' '.join(sampled_texts).lower()
            words    = _re.findall(r"[a-záàéèíïóòúùüçñ'-]+", combined)
            es_hits  = sum(1 for w in words if w in _ES)
            en_hits  = sum(1 for w in words if w in _EN)
            ca_hits  = sum(1 for w in words if w in _CA)
            scores   = {'es': es_hits, 'en': en_hits, 'ca': ca_hits}
            total    = es_hits + en_hits + ca_hits
            if total >= 20:
                best_lang  = max(scores, key=scores.get)
                best_score = scores[best_lang]
                # Second-best score (among the other two languages)
                second_score = max(v for k, v in scores.items() if k != best_lang)
                # Require clear dominance: best must be ≥1.5× second AND
                # account for ≥40% of combined hits to avoid noise triggers.
                if (best_score >= 1.5 * max(second_score, 1)
                        and best_score / total >= 0.40
                        and _base(declared_lang) != best_lang):
                    detected_lang = best_lang
                    method = 'word-frequency'

        if not detected_lang:
            return  # No evidence of a mismatch

        # Mismatch detected — create a warning
        self._add_issue(
            type='language',
            severity='serious',
            location=self.opf_path,
            description=(
                f'The OPF declares language \u201c{self.language}\u201d but the content '
                f'appears to be in \u201c{detected_lang}\u201d '
                f'(detected via {method} across {checked} document(s) sampled). '
                f'Please correct the language using the selector on the Report page.'
            ),
            auto_fixable=False,
            description_key='issue_desc_lang_mismatch',
            description_args={
                'declared': self.language,
                'detected': detected_lang,
                'method': method,
                'checked': checked,
            },
        )

    def _detect_primary_language(self, candidates: List[str]) -> str:
        """
        When the OPF declares multiple dc:language values, heuristically pick
        the primary content language.

        Strategy (in order of confidence):
        1. Read up to 10 spine documents and collect the xml:lang / lang value
           from each <html> element.  The most frequent tag that also appears
           in *candidates* wins.
        2. If the most frequent tag is not in candidates but is a prefix match
           (e.g. "es" matching "es-ES"), use the candidate that starts with it.
        3. Fall back to candidates[0] (EPUB spec: first entry is primary).
        """
        from collections import Counter
        opf_dir = self.opf_path.rsplit('/', 1)[0] if '/' in self.opf_path else ''
        xhtml_ns = 'http://www.w3.org/1999/xhtml'
        xml_ns   = 'http://www.w3.org/XML/1998/namespace'

        # Same safe parser as _check_language_match — prevents DTD attribute
        # injection from EPUB2 XHTML doctypes.
        _safe_parser = etree.XMLParser(
            load_dtd=False,
            no_network=True,
            attribute_defaults=False,
            recover=True,
            remove_blank_text=False,
        )

        lang_counter: Counter = Counter()
        checked = 0
        for idref in (self.spine_idrefs or []):
            item = self.manifest.get(idref, {})
            href = item.get('href', '')
            if not href:
                continue
            abs_href = f'{opf_dir}/{href}' if opf_dir else href
            try:
                data = self.zip.read(abs_href)
                doc  = etree.fromstring(data, _safe_parser)
                # Pass 1: prefer lang on <html> (most authoritative)
                html_el = (doc if (doc.tag == f'{{{xhtml_ns}}}html' or
                                   doc.tag == 'html') else
                           doc.find(f'{{{xhtml_ns}}}html') or doc.find('html'))
                if html_el is not None:
                    lang = (html_el.get(f'{{{xml_ns}}}lang') or
                            html_el.get('lang') or '').strip()
                    if lang:
                        lang_counter[lang] += 1
                        checked += 1
                        if checked >= 10:
                            break
                        continue
                # Pass 2: <html> has no lang — count xml:lang on ALL elements.
                # InDesign often sets xml:lang on individual <p>/<span> elements
                # without setting it on <html>.  The most frequent value that
                # matches a candidate is almost certainly the primary language.
                for el in doc.iter():
                    if not isinstance(el.tag, str):
                        continue
                    lang = (el.get(f'{{{xml_ns}}}lang') or
                            el.get('lang') or '').strip()
                    if lang:
                        lang_counter[lang] += 1
            except Exception:
                pass
            checked += 1
            if checked >= 10:
                break

        # Match counter entries to candidates
        candidates_lower = {c.lower(): c for c in candidates}
        for lang, _ in lang_counter.most_common():
            lang_l = lang.lower()
            # Exact match (case-insensitive)
            if lang_l in candidates_lower:
                return candidates_lower[lang_l]
            # Prefix match: e.g. "es" → "es-ES"
            for cand_l, cand in candidates_lower.items():
                if cand_l.startswith(lang_l + '-') or lang_l.startswith(cand_l + '-'):
                    return cand

        return candidates[0]  # fallback: EPUB spec says first is primary

    # ------------------------------------------------------------------ #
    #  OPF Metadata analysis
    # ------------------------------------------------------------------ #

    def _analyze_opf_metadata(self):
        """Check for required accessibility metadata in the OPF."""
        meta_elements = self.opf_root.findall('.//{http://www.idpf.org/2007/opf}meta')
        existing_properties = set()
        for m in meta_elements:
            prop = m.get('property', '')
            existing_properties.add(prop)

        required_props = [
            ('schema:accessMode', 'critical'),
            ('schema:accessModeSufficient', 'serious'),
            ('schema:accessibilityFeature', 'serious'),
            ('schema:accessibilityHazard', 'moderate'),
            ('dcterms:conformsTo', 'critical'),
        ]

        for prop, severity in required_props:
            if prop not in existing_properties:
                self._add_issue(
                    type='metadata',
                    severity=severity,
                    location=self.opf_path,
                    description=f'Missing required accessibility metadata: {prop}',
                    auto_fixable=True,
                )

        # Check for empty DC metadata fields
        DC_NS_URI = 'http://purl.org/dc/elements/1.1/'
        DC_REQUIRED = {'identifier', 'title', 'language'}
        DC_OPTIONAL = {'creator', 'subject', 'description', 'publisher', 'contributor',
                       'date', 'type', 'format', 'source', 'relation', 'coverage', 'rights'}
        metadata_el = self.opf_root.find('{http://www.idpf.org/2007/opf}metadata')
        if metadata_el is not None:
            for dc_el in metadata_el:
                tag = dc_el.tag
                # Skip comment/PI nodes — lxml returns callable tags for these
                if not isinstance(tag, str):
                    continue
                if not tag.startswith(f'{{{DC_NS_URI}}}'):
                    continue
                local = tag.split('}', 1)[1]
                text = (dc_el.text or '').strip()
                if not text and local in DC_REQUIRED:
                    if local == 'identifier':
                        # Auto-fixed: remediator generates a urn:uuid for empty identifiers
                        self._add_issue(
                            type='metadata',
                            severity='critical',
                            location=self.opf_path,
                            description=f'dc:identifier is empty — a urn:uuid will be generated automatically.',
                            auto_fixable=True,
                            description_key='issue_dc_identifier_empty',
                        )
                    else:
                        self._add_issue(
                            type='metadata',
                            severity='critical',
                            location=self.opf_path,
                            description=f'dc:{local} is empty — required for EPUBCheck validation, must be filled manually.',
                            auto_fixable=False,
                            description_key='issue_dc_required_empty',
                            description_args={'field': local},
                        )
                elif not text and local in DC_OPTIONAL:
                    self._add_issue(
                        type='metadata',
                        severity='minor',
                        location=self.opf_path,
                        description=f'dc:{local} is empty — optional field will be removed during remediation.',
                        auto_fixable=True,
                        description_key='issue_dc_optional_empty',
                        description_args={'field': local},
                    )

        # Check dc:date format (OPF-053: must be W3CDTF / ISO 8601)
        if metadata_el is not None:
            DC_NS_URI_DATE = 'http://purl.org/dc/elements/1.1/'
            date_els = metadata_el.findall(f'{{{DC_NS_URI_DATE}}}date')
            for date_el in date_els:
                raw = (date_el.text or '').strip()
                if not raw:
                    continue
                normalized, is_unambiguous = normalize_dc_date(raw)
                if normalized == raw:
                    continue  # already valid
                if is_unambiguous:
                    self._add_issue(
                        type='metadata',
                        severity='moderate',
                        location=self.opf_path,
                        description=f'dc:date "{raw}" is not W3CDTF format. Will be auto-corrected.',
                        auto_fixable=True,
                        description_key='issue_dc_date_invalid_fixable',
                        description_args={'date': raw},
                    )
                else:
                    self._add_issue(
                        type='metadata',
                        severity='moderate',
                        location=self.opf_path,
                        description=f'dc:date "{raw}" is ambiguous (could be DD-MM-YYYY or MM-DD-YYYY). Manual correction needed.',
                        auto_fixable=False,
                        description_key='issue_dc_date_invalid_ambiguous',
                        description_args={'date': raw},
                    )

        # Check EPUB version compatibility
        if self.epub_version.startswith('2'):
            self._add_issue(
                type='version',
                severity='serious',
                location=self.opf_path,
                description=(
                    f'El documento está en formato EPUB {self.epub_version}. '
                    'EPUB 3 es necesario para una accesibilidad completa. '
                    'El archivo será convertido automáticamente a EPUB 3.'
                ),
                auto_fixable=True,
            )

    # ------------------------------------------------------------------ #
    #  XHTML document analysis
    # ------------------------------------------------------------------ #

    def _analyze_documents(self):
        """Analyze each spine document for accessibility issues."""
        opf_dir = str(PurePosixPath(self.opf_path).parent)

        # Track which image hrefs were found inside spine documents so we can
        # detect cover images declared only in the OPF (EPUB2 pattern).
        spine_image_hrefs: set = set()

        # Build the full list of idrefs to process: spine items first, then
        # the Navigation Document (properties="nav") if it is not already in
        # the spine.  The nav document is never in the spine for many EPUBs
        # but it still needs to be checked for landmark labels, ARIA, etc.
        spine_set = set(self.spine_idrefs)
        nav_idrefs = [
            item_id for item_id, item in self.manifest.items()
            if 'nav' in item.get('properties', '').split()
            and item_id not in spine_set
        ]
        idrefs_to_analyze = self.spine_idrefs + nav_idrefs

        for idref in idrefs_to_analyze:
            if idref not in self.manifest:
                continue
            item = self.manifest[idref]
            if 'html' not in item['media-type']:
                continue

            doc_path = str(PurePosixPath(opf_dir) / item['href']) if opf_dir != '.' else item['href']
            doc_path = doc_path.lstrip('/')

            try:
                doc_data = self.zip.read(doc_path)
            except KeyError:
                # Try alternate path resolution
                try:
                    doc_data = self.zip.read(item['href'])
                    doc_path = item['href']
                except KeyError:
                    continue

            # Use HTMLParser for .html files (HTML4/5 content not valid XML),
            # XMLParser with recovery for .xhtml and everything else.
            try:
                if doc_path.lower().endswith('.html'):
                    parser = etree.HTMLParser(encoding='utf-8')
                    root = etree.fromstring(doc_data, parser)
                else:
                    try:
                        root = etree.fromstring(doc_data)
                    except etree.XMLSyntaxError:
                        parser = etree.XMLParser(recover=True)
                        root = etree.fromstring(doc_data, parser)
            except Exception:
                continue  # Skip completely unparseable documents

            if root is None:
                continue  # lxml recovery returned empty tree

            before = len(self.images_for_review)
            self._analyze_html_document(root, doc_path, opf_dir)
            # Record image hrefs found in this spine doc
            for img_item in self.images_for_review[before:]:
                spine_image_hrefs.add(img_item.epub_src)

        # Fallback: detect cover images declared only in the OPF manifest
        # (EPUB2 pattern: <item id="cover-image" media-type="image/jpeg"/>
        # referenced via <meta name="cover" content="cover-image"/>).
        # If such an image was not found in any spine document, add it for review.
        self._analyze_opf_cover_image(opf_dir, spine_image_hrefs)

    def _analyze_page_list(self):
        """
        Detect whether this EPUB has a page-list nav and whether the OPF
        already declares its source (pageBreakSource).

        Sets self.has_page_list and self.has_page_source accordingly.
        These are stored in the report and used by the dashboard to show
        the pageBreakSource input field when needed.
        """
        OPF_NS_URI  = 'http://www.idpf.org/2007/opf'
        EPUB_NS_URI = 'http://www.idpf.org/2007/ops'

        # 1. Check OPF for existing pageBreakSource declaration
        if self.opf_root is not None:
            for meta in self.opf_root.iter():
                if meta.get('property') == 'pageBreakSource':
                    self.has_page_source = True
                    break

        # 2. Find the nav document in the manifest
        opf_dir = str(PurePosixPath(self.opf_path).parent)
        nav_href = None
        if self.opf_root is not None:
            manifest_el = self.opf_root.find(f'{{{OPF_NS_URI}}}manifest')
            if manifest_el is not None:
                for item in manifest_el.findall(f'{{{OPF_NS_URI}}}item'):
                    if 'nav' in item.get('properties', '').split():
                        nav_href = item.get('href', '')
                        break

        if not nav_href:
            return

        nav_path = str(PurePosixPath(opf_dir) / nav_href).lstrip('/')
        try:
            nav_data = self.zip.read(nav_path)
        except KeyError:
            try:
                nav_data = self.zip.read(nav_href)
            except KeyError:
                return

        try:
            nav_root = etree.fromstring(nav_data)
        except Exception:
            return

        if nav_root is None:
            return

        # 3. Look for <nav epub:type="page-list"> (with or without NS prefix)
        epub_type_attr = f'{{{EPUB_NS_URI}}}type'
        page_list_nav = None
        for el in nav_root.iter():
            tag = el.tag.split('}')[-1] if '}' in el.tag else el.tag
            if tag != 'nav':
                continue
            epub_type = el.get(epub_type_attr) or el.get('epub:type') or ''
            if 'page-list' in epub_type.split():
                self.has_page_list = True
                page_list_nav = el
                break

        # 4. Detect orphaned pagebreaks: pagebreak elements in content not
        #    referenced in the page-list (common InDesign export artifact).
        if page_list_nav is not None:
            XHTML_NS_URI = 'http://www.w3.org/1999/xhtml'
            pagelist_ids = set()
            for a in page_list_nav.iter(f'{{{XHTML_NS_URI}}}a'):
                href = a.get('href', '')
                if '#' in href:
                    pagelist_ids.add(href.split('#', 1)[1])

            # Scan all content docs for unreferenced pagebreaks
            opf_dir_path = str(PurePosixPath(self.opf_path).parent)
            orphan_count = 0
            for item in (self.opf_root.iter() if self.opf_root is not None else []):
                media_type = item.get('media-type', '')
                if media_type not in ('application/xhtml+xml', 'text/html'):
                    continue
                href = item.get('href', '')
                if not href:
                    continue
                doc_zip_path = str(PurePosixPath(opf_dir_path) / href).lstrip('/')
                if doc_zip_path == nav_path:
                    continue
                try:
                    doc_data = self.zip.read(doc_zip_path)
                    doc_root = etree.fromstring(doc_data)
                except Exception:
                    continue
                for el in doc_root.iter():
                    etype = el.get(epub_type_attr, '') or el.get('epub:type', '')
                    role  = el.get('role', '')
                    if 'pagebreak' in etype or 'doc-pagebreak' in role:
                        el_id = el.get('id', '')
                        if el_id and el_id not in pagelist_ids:
                            orphan_count += 1

            if orphan_count:
                self._add_issue(
                    type='html',
                    severity='serious',
                    location=nav_path,
                    description=(
                        f'{orphan_count} pagebreak element(s) found in content '
                        f'without a corresponding entry in the page-list nav '
                        f'(epub-pagelist-missing-pagebreak). '
                        f'These are typically duplicate IDs exported by InDesign.'
                    ),
                    auto_fixable=True,
                    description_key='issue_desc_orphan_pagebreaks',
                    description_args={'n': orphan_count},
                )

    def _analyze_opf_cover_image(self, opf_dir: str, already_found: set):
        """Add cover images declared in the OPF but absent from spine docs."""
        OPF_NS = 'http://www.idpf.org/2007/opf'

        # Find the cover image id via <meta name="cover" content="..."/>
        cover_item_id = None
        metadata_el = self.opf_root.find(f'{{{OPF_NS}}}metadata')
        if metadata_el is not None:
            for m in metadata_el:
                if not isinstance(m.tag, str):
                    continue
                if (m.get('name', '').lower() == 'cover' and m.get('content')):
                    cover_item_id = m.get('content')
                    break

        # Also check manifest items with properties="cover-image" (EPUB3 pattern)
        manifest_el = self.opf_root.find(f'{{{OPF_NS}}}manifest')
        if manifest_el is not None:
            for item in manifest_el.findall(f'{{{OPF_NS}}}item'):
                props = item.get('properties', '').split()
                if 'cover-image' in props:
                    cover_item_id = item.get('id')
                    break

        if not cover_item_id or cover_item_id not in self.manifest:
            return

        cover_item = self.manifest[cover_item_id]
        mt = cover_item.get('media-type', '')
        if 'image' not in mt:
            return

        href = cover_item.get('href', '')
        epub_img_path = (
            str(PurePosixPath(opf_dir) / href) if opf_dir != '.' else href
        ).lstrip('/')

        # Skip if already detected inside a spine document
        if epub_img_path in already_found:
            return

        # Cover image not in any spine doc — add for manual review
        self.images_for_review.append(ImageItem(
            item_id=f'img_{len(self.images_for_review):04d}',
            src=href,
            epub_src=epub_img_path,
            alt=None,
            is_decorative_guess=False,
            context_before='[Cover image declared in OPF manifest]',
            context_after='',
            document=self.opf_path,
        ))
        self._add_issue(
            type='image',
            severity='critical',
            location=self.opf_path,
            description=f'Cover image has no alt text: {href}',
            auto_fixable=False,
        )

    def _analyze_html_document(self, root: etree._Element, doc_path: str, opf_dir: str):
        """Analyze a single XHTML document."""
        xhtml_ns = 'http://www.w3.org/1999/xhtml'
        epub_ns = 'http://www.idpf.org/2007/ops'

        # -- 1. lang attribute on <html> element --
        html_el = root if root.tag in (f'{{{xhtml_ns}}}html', 'html') else root.find(f'{{{xhtml_ns}}}html')
        if html_el is None:
            html_el = root

        lang = html_el.get('lang') or html_el.get('{http://www.w3.org/XML/1998/namespace}lang')
        if not lang:
            self._add_issue(
                type='language',
                severity='critical',
                location=doc_path,
                description='Missing lang attribute on <html> element',
                auto_fixable=True,
                description_key='issue_desc_lang',
            )

        # -- 2. <title> in <head> --
        head = root.find(f'{{{xhtml_ns}}}head')
        if head is None:
            head = root.find('head')
        if head is not None:
            title_el = head.find(f'{{{xhtml_ns}}}title')
            if title_el is None:
                title_el = head.find('title')
            if title_el is None or not (title_el.text and title_el.text.strip()):
                self._add_issue(
                    type='html',
                    severity='serious',
                    location=doc_path,
                    description='Missing or empty <title> element in document head',
                    auto_fixable=True,
                    description_key='issue_desc_title',
                )

        # -- 3. epub:type without matching ARIA role --
        epub_type_attr = f'{{{epub_ns}}}type'
        for el in root.iter():
            epub_type = el.get(epub_type_attr)
            if not epub_type:
                # Also check without namespace (EPUB2 style)
                epub_type = el.get('epub:type')
            if epub_type:
                for etype in epub_type.split():
                    # Strip epub: prefix if present
                    etype_clean = etype.replace('epub:', '')
                    if etype_clean in EPUB_TYPE_TO_ARIA:
                        expected_role = EPUB_TYPE_TO_ARIA[etype_clean]
                        current_role = el.get('role', '')
                        if expected_role not in current_role:
                            self._add_issue(
                                type='aria',
                                severity='moderate',
                                location=doc_path,
                                description=(
                                    f'Element with epub:type="{etype_clean}" is missing '
                                    f'matching ARIA role="{expected_role}"'
                                ),
                                auto_fixable=True,
                            )

        # -- 4. Images --
        self._analyze_images(root, doc_path, opf_dir)

        # -- 5. Tables --
        self._analyze_tables(root, doc_path)

        # -- 6. Nav landmark aria-labels --
        self._analyze_landmarks(root, doc_path)

    def _analyze_landmarks(self, root: etree._Element, doc_path: str):
        """Flag <nav epub:type="..."> elements that have no accessible label.

        Without aria-label / aria-labelledby / title, multiple <nav> elements
        in the same document are indistinguishable for AT (landmark-unique).
        """
        xhtml_ns = 'http://www.w3.org/1999/xhtml'
        epub_ns  = 'http://www.idpf.org/2007/ops'
        epub_type_attr = f'{{{epub_ns}}}type'

        for nav in root.iter(f'{{{xhtml_ns}}}nav', 'nav'):
            epub_type = nav.get(epub_type_attr) or nav.get('epub:type', '')
            if not epub_type:
                continue
            has_label = (
                nav.get('aria-label') or
                nav.get('aria-labelledby') or
                nav.get('title')
            )
            if not has_label:
                self._add_issue(
                    type='landmarks',
                    severity='moderate',
                    location=doc_path,
                    description=(
                        f'<nav epub:type="{epub_type.strip()}"> has no aria-label — '
                        f'landmarks cannot be distinguished by assistive technology '
                        f'(landmark-unique)'
                    ),
                    auto_fixable=True,
                )

    def _analyze_images(self, root: etree._Element, doc_path: str, opf_dir: str):
        """Find all images and classify them."""
        xhtml_ns = 'http://www.w3.org/1999/xhtml'
        img_counter = 0

        for img in root.iter(f'{{{xhtml_ns}}}img', 'img'):
            src = img.get('src', '')
            alt = img.get('alt')  # None if missing, '' if empty
            img_counter += 1

            # Determine EPUB-absolute path of the image (normalized, no '..' segments)
            doc_dir = str(PurePosixPath(doc_path).parent)
            if src.startswith('..') or not src.startswith('/'):
                raw = str(PurePosixPath(doc_dir) / src)
            else:
                raw = src.lstrip('/')
            # os.path.normpath resolves '..' segments (works as posixpath on Linux)
            epub_img_path = os.path.normpath(raw).replace(os.sep, '/')

            # Heuristic: is this likely decorative?
            is_decorative_guess = self._is_likely_decorative(src, img)

            if alt is None:
                # Missing alt attribute - always an issue
                self._add_issue(
                    type='image',
                    severity='critical',
                    location=doc_path,
                    description=f'Image missing alt attribute: {src}',
                    auto_fixable=is_decorative_guess,  # Auto-fix only if likely decorative
                )
                if not is_decorative_guess:
                    # Add to manual review queue
                    context_before, context_after = self._get_context(img)
                    self.images_for_review.append(ImageItem(
                        item_id=f'img_{len(self.images_for_review):04d}',
                        src=src,
                        epub_src=epub_img_path,
                        alt=None,
                        is_decorative_guess=False,
                        context_before=context_before,
                        context_after=context_after,
                        document=doc_path,
                    ))
                else:
                    self._add_issue(
                        type='image',
                        severity='minor',
                        location=doc_path,
                        description=f'Decorative image will be marked with alt="" (auto-fix): {src}',
                        auto_fixable=True,
                    )
            elif alt == '':
                # alt="" looks like a WCAG decorative marking, but tools such as
                # Adobe InDesign set it automatically just to pass ePubCheck — the
                # image may NOT be truly decorative.  Queue it for human (and AI)
                # review, pre-selecting "decorative" as the default so the reviewer
                # can confirm or replace it with real alt text.
                self._add_issue(
                    type='image',
                    severity='moderate',
                    location=doc_path,
                    description=(
                        f'Image has alt="" — may be auto-generated (e.g. InDesign). '
                        f'Verify whether it is truly decorative: {src}'
                    ),
                    auto_fixable=False,
                )
                context_before, context_after = self._get_context(img)
                self.images_for_review.append(ImageItem(
                    item_id=f'img_{len(self.images_for_review):04d}',
                    src=src,
                    epub_src=epub_img_path,
                    alt='',                    # preserve empty string for UI to display
                    is_decorative_guess=True,  # pre-select decorative, but let user verify
                    context_before=context_before,
                    context_after=context_after,
                    document=doc_path,
                ))
            elif alt.strip().lower() in GENERIC_ALT_TEXTS:
                # Alt text exists but is a generic placeholder — surface it
                # for the user to improve, pre-filled with the current value.
                self._add_issue(
                    type='image',
                    severity='minor',
                    location=doc_path,
                    description=(
                        f'Image has a generic/placeholder alt text ("{alt}") '
                        f'that does not describe the image content: {src}'
                    ),
                    auto_fixable=False,
                )
                context_before, context_after = self._get_context(img)
                self.images_for_review.append(ImageItem(
                    item_id=f'img_{len(self.images_for_review):04d}',
                    src=src,
                    epub_src=epub_img_path,
                    alt=alt,                       # keep current generic text
                    is_decorative_guess=False,
                    context_before=context_before,
                    context_after=context_after,
                    document=doc_path,
                    generic_alt=True,
                ))
            # else: non-empty, non-generic alt already present — no action needed

    def _analyze_tables(self, root: etree._Element, doc_path: str):
        """Check tables for accessibility attributes."""
        xhtml_ns = 'http://www.w3.org/1999/xhtml'

        all_tables = list(root.iter(f'{{{xhtml_ns}}}table', 'table'))
        for table_index, table in enumerate(all_tables):
            # Skip tables already marked as presentational
            if table.get('role') in ('presentation', 'none'):
                continue

            needs_review = False

            # Check for caption
            caption_el = (table.find(f'{{{xhtml_ns}}}caption')
                          or table.find('caption'))
            if caption_el is None:
                self._add_issue(
                    type='table',
                    severity='moderate',
                    location=doc_path,
                    description='Table missing <caption> element',
                    auto_fixable=False,
                    description_key='issue_desc_caption',
                )
                needs_review = True

            # Check for missing <th> header elements in multi-row tables.
            # A multi-row table with only <td> cells very likely has a header
            # row that was not marked up correctly by the authoring tool.
            has_th = bool(list(table.iter(f'{{{xhtml_ns}}}th', 'th')))
            row_count = len(list(table.iter(f'{{{xhtml_ns}}}tr', 'tr')))
            first_row_as_headers_guess = not has_th and row_count > 1
            if first_row_as_headers_guess:
                self._add_issue(
                    type='table',
                    severity='serious',
                    location=doc_path,
                    description='Table has no <th> header elements',
                    auto_fixable=False,
                    description_key='issue_desc_missing_th',
                )
                needs_review = True

            if needs_review:
                self._add_table_for_review(root, table, table_index,
                                           doc_path, xhtml_ns,
                                           first_row_as_headers_guess)

            # Check th elements for scope attribute (auto-fixable, no review needed)
            for th in table.iter(f'{{{xhtml_ns}}}th', 'th'):
                if not th.get('scope'):
                    self._add_issue(
                        type='table',
                        severity='serious',
                        location=doc_path,
                        description='Table header <th> missing scope attribute',
                        auto_fixable=True,
                        description_key='issue_desc_th_scope',
                    )

    def _add_table_for_review(self, root, table_el, table_index: int,
                               doc_path: str, xhtml_ns: str,
                               first_row_as_headers_guess: bool = False):
        """Extract table HTML/text/context and add a TableItem to the report."""
        # Serialise table HTML (cap at ~8 KB to avoid huge tables)
        try:
            raw_html = etree.tostring(table_el, encoding='unicode', method='html')
            if len(raw_html) > 8000:
                raw_html = raw_html[:8000] + '…</table>'
        except Exception:
            raw_html = '<table><tr><td>(preview unavailable)</td></tr></table>'

        # Plain-text of headers and cells (for AI)
        def _iter_cells(el, ns):
            for tag in ('th', 'td'):
                for cell in el.iter(f'{{{ns}}}{tag}', tag):
                    txt = ''.join(cell.itertext()).strip()
                    if txt:
                        yield txt

        table_text = ' | '.join(_iter_cells(table_el, xhtml_ns))[:1000]

        # Heuristic: if no <th> but we already flagged first_row_as_headers_guess,
        # this is likely a DATA table with missing markup — don't guess "layout".
        # Only guess layout when there are truly no headers and no header-row candidate.
        has_th = bool(list(table_el.iter(f'{{{xhtml_ns}}}th', 'th')))
        is_layout_guess = not has_th and not first_row_as_headers_guess

        # Context: up to ~150 chars of text before/after the table in the document
        def _prev_text(el):
            parts = []
            prev = el.getprevious()
            while prev is not None and len(' '.join(parts)) < 150:
                t = ''.join(prev.itertext()).strip()
                if t:
                    parts.insert(0, t)
                prev = prev.getprevious()
            return ' '.join(parts)[-150:]

        def _next_text(el):
            parts = []
            nxt = el.getnext()
            while nxt is not None and len(' '.join(parts)) < 150:
                t = ''.join(nxt.itertext()).strip()
                if t:
                    parts.append(t)
                nxt = nxt.getnext()
            return ' '.join(parts)[:150]

        ctx_before = _prev_text(table_el)
        ctx_after  = _next_text(table_el)

        item_id = str(uuid.uuid4())
        self.tables_for_review.append(TableItem(
            item_id=item_id,
            document=doc_path,
            table_index=table_index,
            table_html=raw_html,
            table_text=table_text,
            context_before=ctx_before,
            context_after=ctx_after,
            is_layout_guess=is_layout_guess,
            first_row_as_headers_guess=first_row_as_headers_guess,
        ))

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _is_likely_decorative(self, src: str, img_el: etree._Element) -> bool:
        """Heuristic: guess if an image is decorative."""
        src_lower = src.lower()
        filename = PurePosixPath(src_lower).stem
        for pattern in DECORATIVE_IMAGE_PATTERNS:
            if re.search(pattern, filename):
                return True
        # Very small images (check size via filename patterns like 1x1, pixel, etc.)
        if re.search(r'1x1|pixel|spacer|\.gif$', src_lower):
            return True
        # Images with role="presentation" already set
        if img_el.get('role') == 'presentation':
            return True
        return False

    def _get_context(self, img_el: etree._Element) -> Tuple[str, str]:
        """Extract surrounding text context for an image element.

        Strategy (multi-pass ancestor walk):
        Pass 1 — siblings of <img> within its immediate parent.
                 Prioritises <figcaption> siblings as the most semantically
                 relevant context.  Also captures inline captions like
                 <p><img/> caption text</p>.
        Pass 2+ — if either side is still empty, climb one level up and
                 repeat with the siblings of the current ancestor, up to
                 MAX_ANCESTOR_LEVELS above the image.
                 Captures deeply-nested images such as:
                   <div><div><p><img/></p></div></div>
                   <p class="pie-foto">Caption text here</p>
        """
        def _iter_text(el) -> str:
            return ' '.join(el.itertext()).strip()

        def _local_tag(el) -> str:
            tag = el.tag
            if isinstance(tag, str) and '}' in tag:
                return tag.split('}', 1)[1]
            return tag if isinstance(tag, str) else ''

        parent = img_el.getparent()
        context_before = ''
        context_after = ''

        if parent is None:
            return '', ''

        siblings = list(parent)
        try:
            idx = siblings.index(img_el)
        except ValueError:
            return '', ''

        # Pass 1: siblings of <img> inside its immediate parent.
        # Check for <figcaption> first — it is the canonical image caption.
        for sib_idx, sib in enumerate(siblings):
            if _local_tag(sib) == 'figcaption':
                text = _iter_text(sib)
                if text:
                    # figcaption after the image → context_after; before → context_before
                    if sib_idx < idx:
                        context_before = text[:300]
                    else:
                        context_after = text[:300]

        if not context_before:
            before_parts = []
            for sib in reversed(siblings[:idx][-3:]):
                if _local_tag(sib) == 'figcaption':
                    continue  # already handled above
                text = _iter_text(sib)
                if text:
                    before_parts.append(text)
            context_before = ' '.join(reversed(before_parts))[:300]

        if not context_after:
            after_parts = []
            for sib in siblings[idx + 1:][:3]:
                if _local_tag(sib) == 'figcaption':
                    continue  # already handled above
                text = _iter_text(sib)
                if text:
                    after_parts.append(text)
            context_after = ' '.join(after_parts)[:300]

        # Pass 2+: walk up the ancestor chain until both sides have text or
        # we reach the document root.  Limit to avoid runaway traversal.
        MAX_ANCESTOR_LEVELS = 6
        current = parent
        for _ in range(MAX_ANCESTOR_LEVELS):
            if context_before and context_after:
                break
            ancestor = current.getparent()
            if ancestor is None:
                break
            ac_children = list(ancestor)
            try:
                cur_idx = ac_children.index(current)
            except ValueError:
                break

            if not context_before:
                for sib in reversed(ac_children[:cur_idx][-3:]):
                    text = _iter_text(sib)
                    if text:
                        context_before = text[:300]
                        break
            if not context_after:
                for sib in ac_children[cur_idx + 1:][:3]:
                    text = _iter_text(sib)
                    if text:
                        context_after = text[:300]
                        break

            current = ancestor

        return context_before, context_after

    # ------------------------------------------------------------------ #
    #  NCX uid consistency check (NCX-001)
    # ------------------------------------------------------------------ #

    def _analyze_ncx_uid(self):
        """
        Detect NCX-001: the NCX <meta name="dtb:uid"> does not match the
        text value of the dc:identifier referenced by OPF unique-identifier.
        """
        OPF_NS_URI = 'http://www.idpf.org/2007/opf'
        DC_NS_URI  = 'http://purl.org/dc/elements/1.1/'
        NCX_NS_URI = 'http://www.daisy.org/z3986/2005/ncx/'

        # Resolve the canonical UID from OPF
        uid_ref = self.opf_root.get('unique-identifier', '')
        metadata_el = self.opf_root.find(f'{{{OPF_NS_URI}}}metadata')
        if not uid_ref or metadata_el is None:
            return

        uid_value = None
        for el in metadata_el.findall(f'{{{DC_NS_URI}}}identifier'):
            if el.get('id') == uid_ref:
                uid_value = (el.text or '').strip()
                break
        if not uid_value:
            return

        # Find the NCX file in the manifest
        manifest_el = self.opf_root.find(f'{{{OPF_NS_URI}}}manifest')
        if manifest_el is None:
            return

        opf_dir = str(PurePosixPath(self.opf_path).parent)
        ncx_zip_path = None
        for item in manifest_el.findall(f'{{{OPF_NS_URI}}}item'):
            mt   = item.get('media-type', '')
            href = item.get('href', '')
            if mt == 'application/x-dtbncx+xml' or href.lower().endswith('.ncx'):
                ncx_zip_path = (
                    str(PurePosixPath(opf_dir) / href)
                    if opf_dir != '.' else href
                ).lstrip('/')
                break

        if not ncx_zip_path:
            return

        try:
            ncx_data = self.zip.read(ncx_zip_path)
            ncx_root = etree.fromstring(ncx_data)
        except Exception:
            return

        head_el = ncx_root.find(f'{{{NCX_NS_URI}}}head')
        if head_el is None:
            return

        for meta in head_el.findall(f'{{{NCX_NS_URI}}}meta'):
            if meta.get('name') == 'dtb:uid':
                ncx_uid = meta.get('content', '').strip()
                if ncx_uid != uid_value:
                    self._add_issue(
                        type='ncx',
                        severity='serious',
                        location=ncx_zip_path,
                        description=(
                            f'NCX-001: NCX identifier ("{ncx_uid}") does not match '
                            f'OPF unique identifier ("{uid_value}"). '
                            f'Will be corrected automatically.'
                        ),
                        auto_fixable=True,
                    )
                break

    # ------------------------------------------------------------------ #
    #  CSS contrast analysis
    # ------------------------------------------------------------------ #

    def _analyze_css_files(self):
        """Check all CSS files in the EPUB for WCAG 2.1 AA contrast violations."""
        opf_dir = str(PurePosixPath(self.opf_path).parent)

        for item_id, item in self.manifest.items():
            mt = item.get('media-type', '')
            if 'css' not in mt:
                continue

            href = item.get('href', '')
            css_path = (str(PurePosixPath(opf_dir) / href)
                        if opf_dir != '.' else href).lstrip('/')

            try:
                css_data = self.zip.read(css_path)
                css_text = css_data.decode('utf-8', errors='replace')
            except (KeyError, Exception):
                continue

            violations = analyse_css_text(css_text)
            for v in violations:
                self._add_issue(
                    type='contrast',
                    severity='serious',
                    location=css_path,
                    description=(
                        f'Insufficient color contrast in selector "{v["selector"]}": '
                        f'{v["fg"]} on {v["bg"]} — ratio {v["ratio"]:.2f} '
                        f'(requires ≥ {v["threshold"]:.1f}'
                        f'{", large text" if v["large_text"] else ""})'
                    ),
                    auto_fixable=True,
                )

    def _analyze_inline_styles(self):
        """Detect spine documents that contain inline style attributes."""
        opf_dir = str(PurePosixPath(self.opf_path).parent)

        for idref in self.spine_idrefs:
            if idref not in self.manifest:
                continue
            item = self.manifest[idref]
            if 'html' not in item.get('media-type', ''):
                continue

            doc_path = (str(PurePosixPath(opf_dir) / item['href'])
                        if opf_dir != '.' else item['href']).lstrip('/')

            try:
                doc_data = self.zip.read(doc_path)
            except (KeyError, Exception):
                continue

            # Quick text scan — full parse is expensive; a regex is enough
            # to decide whether to raise a consolidation issue.
            if re.search(rb'\bstyle\s*=\s*["\']', doc_data, re.IGNORECASE):
                self._add_issue(
                    type='contrast',
                    severity='moderate',
                    location=doc_path,
                    description=(
                        'Document contains inline style attributes. '
                        'These will be extracted to the CSS stylesheet '
                        'for uniform contrast analysis (common in EPUB 2 files).'
                    ),
                    auto_fixable=True,
                )

    def _analyze_inline_lang(self) -> None:
        """
        Detect inline xml:lang / lang attributes on content elements that differ
        from the document's declared language.

        InDesign EPUB exports commonly assign xml:lang per paragraph style, so
        every <p> or <span> ends up with a stray language tag (e.g. xml:lang="en"
        in a Spanish book).  Screen readers use these tags to switch the TTS voice
        engine, causing mispronunciation.

        Results are grouped by lang_value and stored as LangItem objects so the
        UI can present them in a compact, bulk-action review panel.
        """
        from collections import defaultdict

        opf_dir  = self.opf_path.rsplit('/', 1)[0] if '/' in self.opf_path else ''
        xhtml_ns = 'http://www.w3.org/1999/xhtml'
        xml_ns   = 'http://www.w3.org/XML/1998/namespace'

        # Declared primary language (base tag only, e.g. "es" from "es-ES").
        declared_base = (self.language or '').lower().split('-')[0]

        _safe_parser = etree.XMLParser(
            load_dtd=False,
            no_network=True,
            attribute_defaults=False,
            recover=True,
            remove_blank_text=False,
        )

        # Accumulate: lang_value → { 'count': int, 'samples': [str], 'docs': set }
        lang_data: dict = defaultdict(lambda: {'count': 0, 'samples': [], 'docs': set()})

        for idref in (self.spine_idrefs or []):
            item = self.manifest.get(idref, {})
            href = item.get('href', '')
            if not href:
                continue
            if 'html' not in item.get('media-type', ''):
                continue
            abs_href = f'{opf_dir}/{href}' if opf_dir else href
            doc_path = abs_href.lstrip('/')

            try:
                data = self.zip.read(abs_href)
                doc  = etree.fromstring(data, _safe_parser)
            except Exception:
                continue

            # Determine this document's own declared language (on <html> element).
            html_el = (doc if (doc.tag == f'{{{xhtml_ns}}}html' or doc.tag == 'html')
                       else doc.find(f'{{{xhtml_ns}}}html') or doc.find('html'))
            doc_lang_base = declared_base  # fallback to OPF declared language
            if html_el is not None:
                hl = (html_el.get(f'{{{xml_ns}}}lang') or
                      html_el.get('lang') or '').strip().lower().split('-')[0]
                if hl:
                    doc_lang_base = hl

            for el in doc.iter():
                if not isinstance(el.tag, str):
                    continue
                # Skip the root <html> element itself — that is handled elsewhere.
                if el is html_el:
                    continue

                lang = (el.get(f'{{{xml_ns}}}lang') or el.get('lang') or '').strip()
                if not lang:
                    continue
                lang_base = lang.lower().split('-')[0]

                # Only flag if it differs from the document's declared language.
                if lang_base == doc_lang_base:
                    continue

                # Collect a text sample (skip empty / near-empty nodes).
                text = (el.text_content() if hasattr(el, 'text_content')
                        else ''.join(el.itertext())).strip()
                # Minimum length guard — skip completely empty elements only.
                # Even 1-char or 2-char content (e.g. "07", "V.") can carry a
                # meaningful xml:lang that the user should review.
                if len(text) < 1:
                    continue

                bucket = lang_data[lang]
                bucket['count'] += 1
                bucket['docs'].add(doc_path)
                if len(bucket['samples']) < 5:
                    sample = text[:120]
                    if sample not in bucket['samples']:
                        bucket['samples'].append(sample)

        # Convert to LangItem objects — include every distinct lang value
        # found at least once.  Single-occurrence values can be legitimate
        # foreign quotes but, for InDesign EPUB exports, even a single stray
        # paragraph style can produce a wrong-language tag.  Let the user decide.
        counter = 0
        for lang_value, bucket in sorted(lang_data.items()):
            if bucket['count'] < 1:
                continue
            counter += 1
            self.lang_items.append(LangItem(
                item_id=f'lang_{counter:04d}',
                lang_value=lang_value,
                element_count=bucket['count'],
                sample_texts=bucket['samples'],
                documents=sorted(bucket['docs']),
            ))

    def _add_issue(self, type: str, severity: str, location: str,
                   description: str, auto_fixable: bool,
                   description_key: str = '',
                   description_args: dict = None) -> Issue:
        self._issue_counter += 1
        issue = Issue(
            issue_id=f'issue_{self._issue_counter:04d}',
            type=type,
            severity=severity,
            location=location,
            description=description,
            auto_fixable=auto_fixable,
            description_key=description_key,
            description_args=description_args or {},
        )
        self.issues.append(issue)
        return issue

    def close(self):
        self.zip.close()
