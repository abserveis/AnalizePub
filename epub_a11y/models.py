"""
Data classes used throughout the tool.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Issue:
    """Represents a single accessibility issue found in the EPUB."""
    issue_id: str
    type: str           # 'metadata' | 'html' | 'image' | 'table' | 'nav' | 'language'
    severity: str       # 'critical' | 'serious' | 'moderate' | 'minor'
    location: str       # file path within EPUB (e.g. 'OEBPS/Text/chapter01.xhtml')
    description: str    # human-readable description
    auto_fixable: bool
    fix_applied: bool = False
    fix_description: str = ''
    description_key: str = ''   # i18n key for translated description (overrides description)
    description_args: Dict[str, Any] = field(default_factory=dict)  # substitution args for description_key
    element_xpath: str = ''


@dataclass
class ImageItem:
    """Represents an image that may need an alt text review."""
    item_id: str
    src: str                   # path within EPUB (relative to document)
    epub_src: str              # absolute path within EPUB zip
    alt: Optional[str]         # current alt attribute value (None = missing)
    is_decorative_guess: bool  # heuristic guess
    context_before: str        # text content before the image in document
    context_after: str         # text content after the image in document
    document: str              # XHTML file containing this image
    reviewed: bool = False
    final_alt: Optional[str] = None
    generic_alt: bool = False    # True when alt text exists but is a placeholder word


@dataclass
class TableItem:
    """Represents a table that needs a caption or role=presentation review."""
    item_id: str
    document: str              # XHTML file containing this table
    table_index: int           # 0-based index of this table among all tables in the document
    table_html: str            # serialised HTML of the table (for preview)
    table_text: str            # plain-text of headers + cells (for AI)
    context_before: str        # text content before the table in the document
    context_after: str         # text content after the table in the document
    is_layout_guess: bool      # heuristic: likely a layout/presentational table
    reviewed: bool = False
    is_layout: Optional[bool] = None   # True = role="presentation", False = data table
    caption: Optional[str] = None      # final caption text (only when is_layout=False)
    first_row_as_headers_guess: bool = False   # no <th> found; first row may be headers
    first_row_as_headers: Optional[bool] = None  # user decision: convert first-row <td>→<th scope="col">"


@dataclass
class LangItem:
    """A group of inline elements that share the same xml:lang value,
    which differs from the document's declared language."""
    item_id: str
    lang_value: str           # e.g. 'en-GB'
    element_count: int        # total elements with this value across all docs
    sample_texts: List[str]   # up to 5 text snippets for preview
    documents: List[str]      # EPUB-relative doc paths containing these elements
    reviewed: bool = False
    remove_attr: Optional[bool] = None  # True=remove attr, False=keep as-is


@dataclass
class AnalysisReport:
    """Full analysis report of an EPUB file."""
    epub_path: str
    epub_version: str    # e.g. '2.0.1' or '3.3'
    title: str
    language: str
    total_documents: int
    total_images: int
    issues: List[Issue] = field(default_factory=list)
    images_for_review: List[ImageItem] = field(default_factory=list)
    tables_for_review: List[TableItem] = field(default_factory=list)
    lang_items: List[LangItem] = field(default_factory=list)
    auto_fix_count: int = 0
    manual_review_count: int = 0
    extra_fixes: List[Any] = field(default_factory=list)  # fixes not tied to a specific Issue (dict or str)
    has_page_list: bool = False      # True if nav.xhtml contains <nav epub:type="page-list">
    has_page_source: bool = False    # True if OPF already declares pageBreakSource
    invalid_dc_date: Optional[str] = None  # Raw invalid dc:date value (ambiguous format; needs user correction)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'epub_path': self.epub_path,
            'epub_version': self.epub_version,
            'title': self.title,
            'language': self.language,
            'total_documents': self.total_documents,
            'total_images': self.total_images,
            'auto_fix_count': self.auto_fix_count,
            'manual_review_count': self.manual_review_count,
            'extra_fixes': list(self.extra_fixes),
            'has_page_list': self.has_page_list,
            'has_page_source': self.has_page_source,
            'invalid_dc_date': self.invalid_dc_date,
            'issues': [
                {
                    'issue_id': i.issue_id,
                    'type': i.type,
                    'severity': i.severity,
                    'location': i.location,
                    'description': i.description,
                    'description_key': i.description_key,
                    'description_args': i.description_args,
                    'auto_fixable': i.auto_fixable,
                    'fix_applied': i.fix_applied,
                    'fix_description': i.fix_description,
                }
                for i in self.issues
            ],
            'images_for_review': [
                {
                    'item_id': img.item_id,
                    'src': img.src,
                    'epub_src': img.epub_src,
                    'alt': img.alt,
                    'is_decorative_guess': img.is_decorative_guess,
                    'context_before': img.context_before,
                    'context_after': img.context_after,
                    'document': img.document,
                    'reviewed': img.reviewed,
                    'final_alt': img.final_alt,
                    'generic_alt': img.generic_alt,
                }
                for img in self.images_for_review
            ],
            'lang_items': [
                {
                    'item_id':       li.item_id,
                    'lang_value':    li.lang_value,
                    'element_count': li.element_count,
                    'sample_texts':  li.sample_texts,
                    'documents':     li.documents,
                    'reviewed':      li.reviewed,
                    'remove_attr':   li.remove_attr,
                }
                for li in self.lang_items
            ],
            'tables_for_review': [
                {
                    'item_id': tbl.item_id,
                    'document': tbl.document,
                    'table_index': tbl.table_index,
                    'table_html': tbl.table_html,
                    'table_text': tbl.table_text,
                    'context_before': tbl.context_before,
                    'context_after': tbl.context_after,
                    'is_layout_guess': tbl.is_layout_guess,
                    'reviewed': tbl.reviewed,
                    'is_layout': tbl.is_layout,
                    'caption': tbl.caption,
                    'first_row_as_headers_guess': tbl.first_row_as_headers_guess,
                    'first_row_as_headers': tbl.first_row_as_headers,
                }
                for tbl in self.tables_for_review
            ],
        }
