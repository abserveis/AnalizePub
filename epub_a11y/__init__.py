"""
epub_a11y - EPUB Accessibility Engine (AnalizePub edition)

This is a *read-only* subset of the AccesPub engine. Only the analyser
and the data models are exposed; the remediation, conversion and report
generation modules from AccesPub are intentionally absent because
AnalizePub never modifies the EPUB file.
"""

__version__ = '0.1.0'
__author__ = 'ab serveis / AnalizePub'

from .analyzer import EPUBAnalyzer
from .models import AnalysisReport, Issue, ImageItem, TableItem, LangItem

__all__ = [
    'EPUBAnalyzer',
    'AnalysisReport',
    'Issue',
    'ImageItem',
    'TableItem',
    'LangItem',
]
