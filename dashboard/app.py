"""
AnalizePub — Free EPUB accessibility audit tool.

This module is the main HTTP entry point. It exposes a small set of routes
on top of the standard library's ThreadingHTTPServer (no Flask, no FastAPI).

Routes
------
GET  /                  Upload page
GET  /report            Render the analysis report for the current session
GET  /report/download   Download the report as a standalone HTML file
GET  /help              Help / FAQ
GET  /legal             Legal notice / privacy
GET  /set-lang?lang=es  Set the UI language (ES / EN / CA)
GET  /static/<file>     Static assets (CSS)
POST /upload            Receive an EPUB, run analysis + EPUBCheck, redirect
                        to /report
POST /reset             Clear current session and redirect to /

PDF generation is handled by the user's browser via window.print() on the
report page; the @media print stylesheet produces a clean printable layout.

Sessions live as plain JSON files under /tmp/analizepub_sessions/<id>/
and expire after 2 hours.
"""

from __future__ import annotations

import datetime as _dt
import html
import io
import json
import logging
import mimetypes
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, quote, urlparse

# ── Path bootstrap ──────────────────────────────────────────────────────────
# Make the project root importable so that both forms work:
#   python -m dashboard.app        (recommended)
#   python dashboard/app.py        (also fine)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Project imports — analyser engine and translations
from epub_a11y import EPUBAnalyzer, AnalysisReport          # noqa: E402
from dashboard.i18n import (                                # noqa: E402
    DEFAULT_LANG,
    SUPPORTED_LANGS,
    lang_from_cookie_or_header,
    t,
)

# Optional: epubcheck wrapper (requires Java at runtime).
try:
    from epubcheck import EpubCheck   # type: ignore
    EPUBCHECK_IMPORT_OK = True
except Exception:  # pragma: no cover - optional dependency
    EPUBCHECK_IMPORT_OK = False


# ─────────────────────────────────────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────────────────────────────────────

HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', '8080'))

SESSIONS_DIR = Path(os.environ.get(
    'ANALIZEPUB_SESSIONS_DIR', '/tmp/analizepub_sessions'
))
MAX_UPLOAD_BYTES = int(os.environ.get(
    'ANALIZEPUB_MAX_UPLOAD_BYTES', str(50 * 1024 * 1024)
))
SESSION_TTL_SECONDS = int(os.environ.get(
    'ANALIZEPUB_SESSION_TTL', '7200'  # 2 hours
))

STATIC_DIR = Path(__file__).resolve().parent / 'static'
COOKIE_SESSION = 'apub_sid'
COOKIE_LANG = 'apub_lang'

# ── Production URLs and tracking IDs ────────────────────────────────────────
SITE_URL = os.environ.get('ANALIZEPUB_SITE_URL', 'https://analizepub.app')
GTM_ID   = os.environ.get('ANALIZEPUB_GTM_ID',   'GTM-MZKJ6H5Z')
GA_ID    = os.environ.get('ANALIZEPUB_GA_ID',    'G-BQ6NW9DEKP')

# Map UI language → Open Graph locale
_OG_LOCALE = {'es': 'es_ES', 'en': 'en_US', 'ca': 'ca_ES'}

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s [%(levelname)s] %(message)s',
)
log = logging.getLogger('analizepub')


# ─────────────────────────────────────────────────────────────────────────────
#  Session manager
# ─────────────────────────────────────────────────────────────────────────────

class SessionManager:
    """Plain-file session storage under /tmp.

    A session is a directory with three JSON files:
      * report.json      - serialised AnalysisReport
      * validation.json  - serialised EPUBCheck result
      * meta.json        - {filename, created_at, indicators}
    """

    def __init__(self, root: Path, ttl: int) -> None:
        self.root = root
        self.ttl = ttl
        self.root.mkdir(parents=True, exist_ok=True)

    # ── lifecycle ────────────────────────────────────────────────────────
    def new_id(self) -> str:
        return uuid.uuid4().hex

    def session_dir(self, sid: str) -> Path:
        return self.root / sid

    def save(self, sid: str, *, report: dict, validation: dict, meta: dict) -> None:
        d = self.session_dir(sid)
        d.mkdir(parents=True, exist_ok=True)
        (d / 'report.json').write_text(
            json.dumps(report, ensure_ascii=False), encoding='utf-8'
        )
        (d / 'validation.json').write_text(
            json.dumps(validation, ensure_ascii=False), encoding='utf-8'
        )
        (d / 'meta.json').write_text(
            json.dumps(meta, ensure_ascii=False), encoding='utf-8'
        )

    def load(self, sid: str) -> dict | None:
        if not sid or not re.fullmatch(r'[0-9a-f]{32}', sid):
            return None
        d = self.session_dir(sid)
        if not d.is_dir():
            return None
        try:
            report = json.loads((d / 'report.json').read_text(encoding='utf-8'))
            validation = json.loads(
                (d / 'validation.json').read_text(encoding='utf-8')
            )
            meta = json.loads((d / 'meta.json').read_text(encoding='utf-8'))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        return {'report': report, 'validation': validation, 'meta': meta}

    def delete(self, sid: str) -> None:
        if not sid:
            return
        d = self.session_dir(sid)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)

    def cleanup_expired(self) -> int:
        """Remove sessions older than TTL. Returns count removed."""
        now = time.time()
        removed = 0
        if not self.root.is_dir():
            return 0
        for entry in self.root.iterdir():
            if not entry.is_dir():
                continue
            try:
                age = now - entry.stat().st_mtime
            except OSError:
                continue
            if age > self.ttl:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
        return removed


sessions = SessionManager(SESSIONS_DIR, SESSION_TTL_SECONDS)


# ─────────────────────────────────────────────────────────────────────────────
#  EPUBCheck wrapper
# ─────────────────────────────────────────────────────────────────────────────

def run_epubcheck(epub_path: str) -> dict:
    """Run EPUBCheck and return a normalised dict.

    Output shape:
        {
          'available': bool,
          'valid': bool | None,
          'errors': int, 'warnings': int, 'fatals': int,
          'infos': int, 'usages': int,
          'messages': [
             {'severity', 'id', 'location', 'message'}, ...
          ]
        }
    If EPUBCheck cannot run (no Java, missing dependency), `available=False`.
    """
    base = {
        'available': False, 'valid': None,
        'errors': 0, 'warnings': 0, 'fatals': 0,
        'infos': 0, 'usages': 0,
        'messages': [],
    }
    if not EPUBCHECK_IMPORT_OK:
        return base
    try:
        result = EpubCheck(epub_path)
    except Exception as exc:  # pragma: no cover - environment dependent
        log.warning('EPUBCheck failed: %s', exc)
        return base

    msgs: list[dict] = []
    for m in (result.messages or []):
        severity = (getattr(m, 'level', None) or '').upper() or 'INFO'
        msgs.append({
            'severity': severity,
            'id': getattr(m, 'id', '') or '',
            'location': _format_epubcheck_location(m),
            'message': getattr(m, 'message', '') or '',
        })

    counts = {'FATAL': 0, 'ERROR': 0, 'WARNING': 0, 'INFO': 0, 'USAGE': 0}
    for m in msgs:
        counts[m['severity']] = counts.get(m['severity'], 0) + 1

    return {
        'available': True,
        'valid': bool(getattr(result, 'valid', None)),
        'errors': counts.get('ERROR', 0),
        'warnings': counts.get('WARNING', 0),
        'fatals': counts.get('FATAL', 0),
        'infos': counts.get('INFO', 0),
        'usages': counts.get('USAGE', 0),
        'messages': msgs,
    }


def _format_epubcheck_location(m: Any) -> str:
    """Produce 'file.xhtml:line:col' (or partial) from an EPUBCheck message."""
    file_ = getattr(m, 'location', None) or getattr(m, 'file', '')
    line = getattr(m, 'line', None)
    col = getattr(m, 'column', None) or getattr(m, 'col', None)
    parts: list[str] = []
    if file_:
        parts.append(str(file_))
    if line and line != -1:
        parts.append(str(line))
    if col and col != -1:
        parts.append(str(col))
    return ':'.join(parts)


# ─────────────────────────────────────────────────────────────────────────────
#  Indicators (semáforos)
# ─────────────────────────────────────────────────────────────────────────────

# Issue-type buckets used to score the EAA and WCAG indicators.
#
# Note: `version` (EPUB 2 detected → conversion suggested) is intentionally
# NOT in EAA_TYPES.  EPUB Accessibility 1.1 explicitly states it is applicable
# to any EPUB, including EPUB 2: a properly-tagged EPUB 2 *can* be conformant.
# EPUB 3 only makes compliance easier in practice — it is not a requirement.
# So an EPUB-2 file should not, by itself, push the EAA indicator into red.
EAA_TYPES = {'metadata', 'language'}
WCAG_TYPES = {'image', 'table', 'nav', 'html', 'css', 'aria'}


def compute_indicators(report: dict, validation: dict) -> dict:
    """Return three traffic-light statuses: eaa, wcag, epubcheck.

    Each value is one of 'ok', 'warn', 'error'.
    """
    issues = report.get('issues', []) or []

    # ── EAA: critical/serious metadata, version or language issues ──
    eaa_critical = sum(
        1 for i in issues
        if i.get('type') in EAA_TYPES and i.get('severity') in ('critical', 'serious')
    )
    eaa_moderate = sum(
        1 for i in issues
        if i.get('type') in EAA_TYPES and i.get('severity') in ('moderate', 'minor')
    )
    if eaa_critical > 0:
        eaa_status = 'error'
    elif eaa_moderate > 0:
        eaa_status = 'warn'
    else:
        eaa_status = 'ok'

    # ── WCAG: critical/serious image/table/nav/html/css/aria issues ──
    wcag_critical = sum(
        1 for i in issues
        if i.get('type') in WCAG_TYPES and i.get('severity') in ('critical', 'serious')
    )
    wcag_moderate = sum(
        1 for i in issues
        if i.get('type') in WCAG_TYPES and i.get('severity') in ('moderate', 'minor')
    )
    # Manual reviews count as warnings, not errors.
    has_manual_review = bool(
        report.get('images_for_review')
        or report.get('tables_for_review')
        or report.get('lang_items')
    )
    if wcag_critical > 0:
        wcag_status = 'error'
    elif wcag_moderate > 0 or has_manual_review:
        wcag_status = 'warn'
    else:
        wcag_status = 'ok'

    # ── EPUBCheck ──
    if not validation.get('available'):
        epc_status = 'unavailable'
    elif validation.get('errors', 0) > 0 or validation.get('fatals', 0) > 0:
        epc_status = 'error'
    elif validation.get('warnings', 0) > 0:
        epc_status = 'warn'
    else:
        epc_status = 'ok'

    return {
        'eaa': eaa_status,
        'wcag': wcag_status,
        'epubcheck': epc_status,
        'eaa_critical': eaa_critical,
        'eaa_moderate': eaa_moderate,
        'wcag_critical': wcag_critical,
        'wcag_moderate': wcag_moderate,
        'has_manual_review': has_manual_review,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Multipart parser (single file field) — minimal, no cgi dependency
# ─────────────────────────────────────────────────────────────────────────────

class MultipartError(Exception):
    pass


def parse_multipart(stream: io.BufferedReader, boundary: bytes,
                    *, content_length: int,
                    max_bytes: int) -> tuple[str | None, bytes | None]:
    """Extract (filename, file_bytes) for the first 'file' field of a
    multipart/form-data POST. Other fields are ignored.

    `content_length` is mandatory: HTTP keep-alive connections never EOF, so
    we MUST stop reading after exactly this many bytes.

    Raises MultipartError if the body is malformed or larger than `max_bytes`.
    """
    if content_length <= 0:
        raise MultipartError('Empty body')
    if content_length > max_bytes:
        raise MultipartError('Body too large')

    delim = b'--' + boundary
    buf = bytearray()
    remaining = content_length
    while remaining > 0:
        chunk = stream.read(min(remaining, 64 * 1024))
        if not chunk:
            break
        buf.extend(chunk)
        remaining -= len(chunk)

    body = bytes(buf)
    parts = body.split(delim)
    for part in parts:
        if not part or part.strip() in (b'', b'--', b'--\r\n'):
            continue
        if part.startswith(b'\r\n'):
            part = part[2:]
        if part.endswith(b'\r\n'):
            part = part[:-2]
        if part.startswith(b'--'):
            # final boundary marker
            continue
        # Split headers / body
        sep = part.find(b'\r\n\r\n')
        if sep == -1:
            continue
        headers_blob = part[:sep].decode('utf-8', 'replace')
        content = part[sep + 4:]
        # Trim trailing CRLF if present
        if content.endswith(b'\r\n'):
            content = content[:-2]
        # Find Content-Disposition
        disp_match = re.search(
            r'Content-Disposition:\s*form-data;([^\r\n]+)',
            headers_blob, flags=re.IGNORECASE,
        )
        if not disp_match:
            continue
        params = disp_match.group(1)
        name_match = re.search(r'name="([^"]*)"', params)
        filename_match = re.search(r'filename="([^"]*)"', params)
        if not name_match:
            continue
        if name_match.group(1) != 'file':
            continue
        filename = filename_match.group(1) if filename_match else None
        return filename, content
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
#  EPUB sanity checks (size, fixed-layout, etc.) — performed before analyse
# ─────────────────────────────────────────────────────────────────────────────

def is_fixed_layout(epub_path: str) -> bool:
    """Return True if the EPUB declares rendition:layout=pre-paginated."""
    try:
        with zipfile.ZipFile(epub_path, 'r') as zf:
            # Find the OPF via container.xml
            try:
                container = zf.read('META-INF/container.xml')
            except KeyError:
                return False
            m = re.search(rb'full-path="([^"]+)"', container)
            if not m:
                return False
            opf_path = m.group(1).decode('utf-8')
            try:
                opf = zf.read(opf_path).decode('utf-8', 'replace')
            except KeyError:
                return False
            return bool(re.search(
                r'<meta[^>]+property\s*=\s*["\']rendition:layout["\'][^>]*>'
                r'\s*pre-paginated\s*</meta>',
                opf, flags=re.IGNORECASE,
            ))
    except (zipfile.BadZipFile, OSError):
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  HTML helpers / templates
# ─────────────────────────────────────────────────────────────────────────────

def E(s: str | None) -> str:
    """HTML-escape, treating None as ''."""
    return html.escape('' if s is None else str(s), quote=True)


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')


def layout(*, lang: str, title: str, body: str,
           active_nav: str = '',
           inline_assets: bool = False,
           canonical_path: str = '/',
           noindex: bool = False) -> str:
    """Page chrome shared by every UI page.

    Modes
    -----
    Live web view (default)
        Links to /static/style.css, loads Lucide via CDN, includes SEO
        meta tags + Google Tag Manager + Google Analytics.
    Download HTML (`inline_assets=True`)
        Inlines the stylesheet so the file is self-contained when opened
        from disk. Uses the slim chrome variants. SEO and tracking are
        intentionally OFF — the file is meant to be read offline, not
        crawled or instrumented.
    """
    description = t(lang, 'brand_tagline')

    if inline_assets:
        try:
            css = (STATIC_DIR / 'style.css').read_text(encoding='utf-8')
            head_assets = f'<style>{css}</style>'
        except OSError:
            head_assets = (
                f'<link rel="stylesheet" href="{SITE_URL}/static/style.css">'
            )
        chrome = _render_header(lang, active_nav, slim=True)
        footer = _render_footer(lang, slim=True)
        scripts = ''
        seo_block = ''
        tracking_head = ''
        tracking_noscript = ''
        consent_banner = ''
    else:
        head_assets = '<link rel="stylesheet" href="/static/style.css">'
        chrome = _render_header(lang, active_nav)
        footer = _render_footer(lang)
        scripts = _LUCIDE_SCRIPT
        seo_block = _render_seo(lang, title, description, canonical_path, noindex)
        tracking_head = _render_tracking_head()
        tracking_noscript = _render_tracking_noscript()
        consent_banner = _render_consent_banner(lang)

    return f"""<!doctype html>
<html lang="{E(lang)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{tracking_head}
<title>{E(title)}</title>
<meta name="description" content="{E(description)}">
{seo_block}
{head_assets}
</head>
<body>
{tracking_noscript}
{chrome}
<main id="main-content" class="container" tabindex="-1">
{body}
</main>
{footer}
{consent_banner}
{scripts}
</body>
</html>
"""


def _render_seo(lang: str, title: str, description: str,
                canonical_path: str, noindex: bool) -> str:
    """Canonical + Open Graph + Twitter Card meta tags."""
    canonical = f'{SITE_URL}{canonical_path}'
    locale = _OG_LOCALE.get(lang, 'es_ES')
    robots = 'noindex, nofollow' if noindex else 'index, follow'
    og_image = f'{SITE_URL}/static/og-image.png'  # will fall back gracefully
    return (
        f'<meta name="robots" content="{robots}">\n'
        f'<link rel="canonical" href="{canonical}">\n'
        f'<meta name="theme-color" content="#0f172a">\n'
        f'<meta property="og:type" content="website">\n'
        f'<meta property="og:site_name" content="AnalizePub">\n'
        f'<meta property="og:url" content="{canonical}">\n'
        f'<meta property="og:title" content="{E(title)}">\n'
        f'<meta property="og:description" content="{E(description)}">\n'
        f'<meta property="og:locale" content="{locale}">\n'
        f'<meta property="og:image" content="{og_image}">\n'
        f'<meta name="twitter:card" content="summary_large_image">\n'
        f'<meta name="twitter:title" content="{E(title)}">\n'
        f'<meta name="twitter:description" content="{E(description)}">\n'
        f'<meta name="twitter:image" content="{og_image}">'
    )


def _render_tracking_head() -> str:
    """Consent Mode v2 + GTM + GA (gtag.js).

    Order of execution in <head>:
      1. dataLayer + gtag bootstrap
      2. Consent default — analytics_storage starts DENIED until the user
         opts in via the cookie banner. Reads previous choice from
         localStorage so returning visitors don't see the banner again.
      3. The class `consent-pending` is added to <html> when there is no
         saved choice → CSS reveals the banner without flicker.
      4. GTM init script (only after consent default is set).
      5. gtag.js loaded async, then `gtag('config', GA_ID)`.

    The exposed globals `apubConsent(d)` and `apubShowConsent()` are used
    by the banner buttons and by the "Cookie settings" link in the footer.
    """
    return (
        '<!-- Consent Mode v2 + GTM + GA -->\n'
        '<script>\n'
        '  window.dataLayer = window.dataLayer || [];\n'
        '  function gtag(){dataLayer.push(arguments);}\n'
        '\n'
        '  var apubSavedConsent = null;\n'
        '  try { apubSavedConsent = localStorage.getItem("apub_consent"); }\n'
        '  catch (e) {}\n'
        '\n'
        '  gtag("consent", "default", {\n'
        '    "ad_storage":            "denied",\n'
        '    "ad_user_data":          "denied",\n'
        '    "ad_personalization":    "denied",\n'
        '    "analytics_storage":     apubSavedConsent === "granted" ? "granted" : "denied",\n'
        '    "functionality_storage": "granted",\n'
        '    "personalization_storage":"denied",\n'
        '    "security_storage":      "granted"\n'
        '  });\n'
        '\n'
        '  if (!apubSavedConsent) {\n'
        '    document.documentElement.classList.add("consent-pending");\n'
        '  }\n'
        '\n'
        '  // Globals used by the banner buttons and the footer link.\n'
        '  window.apubConsent = function (decision) {\n'
        '    try { localStorage.setItem("apub_consent", decision); } catch (e) {}\n'
        '    gtag("consent", "update", {\n'
        '      "analytics_storage": decision === "granted" ? "granted" : "denied"\n'
        '    });\n'
        '    document.documentElement.classList.remove("consent-pending");\n'
        '  };\n'
        '  window.apubShowConsent = function () {\n'
        '    document.documentElement.classList.add("consent-pending");\n'
        '  };\n'
        '\n'
        '  // GTM bootstrap (after consent default).\n'
        '  (function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({"gtm.start":\n'
        '  new Date().getTime(),event:"gtm.js"});var f=d.getElementsByTagName(s)[0],\n'
        '  j=d.createElement(s),dl=l!="dataLayer"?"&l="+l:"";j.async=true;j.src=\n'
        '  "https://www.googletagmanager.com/gtm.js?id="+i+dl;f.parentNode.insertBefore(j,f);\n'
        f'  }})(window,document,"script","dataLayer","{GTM_ID}");\n'
        '</script>\n'
        '<!-- End Consent + GTM -->\n'
        '<!-- Google tag (gtag.js) -->\n'
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>\n'
        '<script>\n'
        '  gtag("js", new Date());\n'
        f'  gtag("config", "{GA_ID}");\n'
        '</script>'
    )


def _render_tracking_noscript() -> str:
    """GTM noscript fallback — must go right after <body>."""
    return (
        '<!-- Google Tag Manager (noscript) -->\n'
        f'<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={GTM_ID}"\n'
        'height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>\n'
        '<!-- End Google Tag Manager (noscript) -->'
    )


def _render_consent_banner(lang: str) -> str:
    """Cookie consent banner — visible only when <html> has the
    `consent-pending` class (set by the bootstrap script in head when no
    saved choice exists). The buttons call the globals `apubConsent` and
    a link in the footer calls `apubShowConsent` to re-open it.
    """
    return f"""
<div id="cookie-banner" class="cookie-banner"
     role="dialog"
     aria-modal="false"
     aria-labelledby="cookie-banner-title"
     aria-describedby="cookie-banner-desc">
  <div class="cookie-banner-text">
    <h2 id="cookie-banner-title" class="cookie-banner-title">{E(t(lang, 'cookie_title'))}</h2>
    <p id="cookie-banner-desc">{E(t(lang, 'cookie_text'))}</p>
  </div>
  <div class="cookie-banner-actions">
    <button type="button" class="btn btn-primary btn-sm"
            onclick="apubConsent('granted')">{E(t(lang, 'cookie_accept'))}</button>
    <button type="button" class="btn btn-secondary btn-sm"
            onclick="apubConsent('denied')">{E(t(lang, 'cookie_reject'))}</button>
    <a href="/legal" class="btn btn-ghost btn-sm">{E(t(lang, 'cookie_more'))}</a>
  </div>
</div>
"""


def _render_robots_txt() -> str:
    """Robots.txt — index public pages, hide session-specific ones."""
    return (
        'User-agent: *\n'
        'Allow: /\n'
        'Disallow: /report\n'
        'Disallow: /report/\n'
        'Disallow: /upload\n'
        'Disallow: /reset\n'
        'Disallow: /set-lang\n'
        '\n'
        f'Sitemap: {SITE_URL}/sitemap.xml\n'
    )


def _render_sitemap_xml() -> str:
    """Sitemap with the three indexable pages."""
    today = _dt.date.today().isoformat()
    urls = [
        ('/',      '1.0', 'monthly'),
        ('/help',  '0.7', 'monthly'),
        ('/legal', '0.3', 'yearly'),
    ]
    items = []
    for path, prio, freq in urls:
        items.append(
            f'  <url>\n'
            f'    <loc>{SITE_URL}{path}</loc>\n'
            f'    <lastmod>{today}</lastmod>\n'
            f'    <changefreq>{freq}</changefreq>\n'
            f'    <priority>{prio}</priority>\n'
            f'  </url>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + '\n'.join(items) + '\n'
        '</urlset>\n'
    )


# Lucide UMD via unpkg (the official browser-CDN documented by Lucide).
# Pinning to a stable version keeps the visual output reproducible.
_LUCIDE_VERSION = '0.469.0'
_LUCIDE_SCRIPT = (
    f'<script src="https://unpkg.com/lucide@{_LUCIDE_VERSION}/dist/umd/lucide.min.js"'
    ' crossorigin="anonymous"></script>'
    '<script>'
    'document.addEventListener("DOMContentLoaded",function(){'
    'if(window.lucide&&typeof lucide.createIcons==="function"){lucide.createIcons();}'
    '});'
    '</script>'
)


def _render_header(lang: str, active: str, *, slim: bool = False) -> str:
    """Top page chrome.

    `slim=True` strips the nav and the language selector — used for the
    downloadable HTML report so the file does not look like a live dashboard
    when opened from disk.
    """
    if slim:
        return f"""
<header role="banner" class="header-slim">
  <div class="header-inner container">
    <span class="brand" aria-label="AnalizePub">
      <span class="brand-name">{E(t(lang, 'brand_name'))}</span>
      <span class="brand-by">{E(t(lang, 'brand_by'))}</span>
    </span>
  </div>
</header>
"""

    # Main nav links — `aria-current="page"` exposes the active item to AT.
    nav_items = [
        ('home',  '/',     t(lang, 'nav_home')),
        ('help',  '/help', t(lang, 'nav_help')),
        ('legal', '/legal', t(lang, 'nav_legal')),
    ]
    nav_pieces = []
    for key, url, label in nav_items:
        is_active = (key == active)
        active_class = ' active' if is_active else ''
        aria_current = ' aria-current="page"' if is_active else ''
        nav_pieces.append(
            f'<a href="{E(url)}" class="nav-link{active_class}"{aria_current}>'
            f'{E(label)}</a>'
        )
    nav_html = ''.join(nav_pieces)

    # Two language pickers, only one shown at a time:
    #   * .lang-buttons → desktop, three short pills (ES / EN / CA)
    #   * .lang-form    → mobile, native <select> dropdown
    pill_pieces = []
    for l in SUPPORTED_LANGS:
        is_current = (l == lang)
        active_class = ' lang-btn-active' if is_current else ''
        aria_current = ' aria-current="true"' if is_current else ''
        full_name = E(t(lang, 'lang_' + l))
        short = E(t(lang, 'lang_short_' + l))
        pill_pieces.append(
            f'<li><a href="/set-lang?lang={l}" '
            f'class="lang-btn{active_class}" data-lang="{l}"{aria_current} '
            f'aria-label="{full_name}">{short}</a></li>'
        )
    lang_buttons_html = ''.join(pill_pieces)

    option_pieces = []
    for l in SUPPORTED_LANGS:
        sel = ' selected' if l == lang else ''
        option_pieces.append(
            f'<option value="{l}"{sel}>{E(t(lang, "lang_" + l))}</option>'
        )
    lang_options = ''.join(option_pieces)

    confirm_msg_report = js_str(t(lang, 'confirm_lang_report'))
    confirm_msg_file = js_str(t(lang, 'confirm_lang_file'))

    return f"""
<a href="#main-content" class="skip-link">{E(t(lang, 'skip_to_main'))}</a>
<header role="banner">
  <div class="header-inner container">
    <a class="brand" href="/" aria-label="{E(t(lang, 'aria_brand'))}">
      <span class="brand-name">{E(t(lang, 'brand_name'))}</span>
      <span class="brand-by">{E(t(lang, 'brand_by'))}</span>
    </a>
    <nav class="main-nav" aria-label="{E(t(lang, 'aria_main_nav'))}">{nav_html}</nav>
    <div class="lang-switch">
      <ul class="lang-buttons" role="group" aria-label="{E(t(lang, 'lang_label'))}">
        {lang_buttons_html}
      </ul>
      <form class="lang-form" method="get" action="/set-lang" id="lang-form">
        <label for="lang-select" class="visually-hidden">{E(t(lang, 'lang_label'))}</label>
        <select id="lang-select" name="lang">{lang_options}</select>
        <noscript><button type="submit">OK</button></noscript>
      </form>
    </div>
  </div>
</header>
<script>
(function(){{
  function shouldConfirm(){{
    var path = window.location.pathname;
    if (path === '/report' || path.indexOf('/report/') === 0) {{
      return '{confirm_msg_report}';
    }}
    var f = document.getElementById('file');
    if (f && f.files && f.files.length) return '{confirm_msg_file}';
    return null;
  }}
  // Mobile dropdown
  var sel = document.getElementById('lang-select');
  if (sel) {{
    var current = sel.value;
    sel.addEventListener('change', function(e){{
      var msg = shouldConfirm();
      if (msg && !window.confirm(msg)) {{ sel.value = current; e.preventDefault(); return; }}
      document.getElementById('lang-form').submit();
    }});
  }}
  // Desktop pills
  var pills = document.querySelectorAll('.lang-btn');
  for (var i = 0; i < pills.length; i++) {{
    pills[i].addEventListener('click', function(e){{
      if (this.classList.contains('lang-btn-active')) {{ e.preventDefault(); return; }}
      var msg = shouldConfirm();
      if (msg && !window.confirm(msg)) {{ e.preventDefault(); return; }}
    }});
  }}
}})();
</script>
"""


def _render_footer(lang: str, *, slim: bool = False) -> str:
    """Bottom page chrome.

    `slim=True` removes the legal-notice link — used for the downloadable
    HTML report (the legal page lives on the live website).
    """
    year = _dt.date.today().year
    brand = (
        f'<a href="https://abserveis.net/" rel="external" class="footer-brand">'
        f'ab serveis</a>'
    )
    copy = f'© {year} {brand} · {E(t(lang, "footer_text"))}'

    if slim:
        return f"""
<footer role="contentinfo" class="footer-slim">
  <div class="container footer-inner">
    <span>{copy}</span>
    <span class="footer-links">
      <a href="https://accespub.app" rel="external">{E(t(lang, 'footer_accespub'))}</a>
    </span>
  </div>
</footer>
"""
    return f"""
<footer role="contentinfo">
  <div class="container footer-inner">
    <span>{copy}</span>
    <span class="footer-links">
      <a href="/legal">{E(t(lang, 'footer_legal'))}</a>
      <a href="#" onclick="apubShowConsent();return false;">{E(t(lang, 'footer_cookies'))}</a>
      <a href="https://accespub.app" rel="external">{E(t(lang, 'footer_accespub'))}</a>
    </span>
  </div>
</footer>
"""


# ── Upload page ──────────────────────────────────────────────────────────────

def render_upload(lang: str, *, error: str | None = None) -> str:
    error_html = (
        f'<div class="alert alert-error" role="alert">{E(error)}</div>'
        if error else ''
    )
    body = f"""
<section class="hero">
  <h1>{E(t(lang, 'upload_h1'))}</h1>
  <p class="lead">{E(t(lang, 'upload_subtitle'))}</p>
</section>

{error_html}

<form id="upload-form" class="upload-card" method="post" action="/upload"
      enctype="multipart/form-data">
  <label for="file" class="dropzone" id="dropzone">
    <i data-lucide="upload-cloud" aria-hidden="true"></i>
    <span class="dropzone-title">{E(t(lang, 'upload_click'))}</span>
    <span class="dropzone-hint">{E(t(lang, 'upload_drag_hint'))}</span>
    <input type="file" id="file" name="file"
           accept=".epub,application/epub+zip"
           class="visually-hidden" required>
    <span id="file-chosen" class="dropzone-chosen" aria-live="polite"></span>
  </label>
  <div class="upload-notes">
    <p>{E(t(lang, 'upload_hint'))}</p>
    <p>{E(t(lang, 'upload_fixed_note'))}</p>
    <p class="privacy">{E(t(lang, 'upload_privacy_note'))}</p>
  </div>
  <button type="submit" class="btn btn-primary btn-lg">{t(lang, 'upload_analyze')}</button>
  <div id="loader" class="loader hidden" role="status" aria-live="polite">
    <div class="spinner"></div>
    <p>{E(t(lang, 'loading_text'))}</p>
    <p class="loader-hint">{E(t(lang, 'loading_hint'))}</p>
  </div>
</form>

<section class="features">
  <h2>{E(t(lang, 'what_h2'))}</h2>
  <p>{E(t(lang, 'what_intro'))}</p>
  <ul class="features-list">
    <li><i data-lucide="file-text"></i><span>{E(t(lang, 'what_li_metadata'))}</span></li>
    <li><i data-lucide="languages"></i><span>{E(t(lang, 'what_li_lang'))}</span></li>
    <li><i data-lucide="layout-list"></i><span>{E(t(lang, 'what_li_semantics'))}</span></li>
    <li><i data-lucide="image"></i><span>{E(t(lang, 'what_li_images'))}</span></li>
    <li><i data-lucide="table-2"></i><span>{E(t(lang, 'what_li_tables'))}</span></li>
    <li><i data-lucide="contrast"></i><span>{E(t(lang, 'what_li_contrast'))}</span></li>
    <li><i data-lucide="list-tree"></i><span>{E(t(lang, 'what_li_nav'))}</span></li>
    <li><i data-lucide="check-circle-2"></i><span>{E(t(lang, 'what_li_epubcheck'))}</span></li>
  </ul>
</section>

<script>
(function(){{
  const input = document.getElementById('file');
  const dz = document.getElementById('dropzone');
  const chosen = document.getElementById('file-chosen');
  const form = document.getElementById('upload-form');
  const loader = document.getElementById('loader');
  const MAX = {MAX_UPLOAD_BYTES};
  function setName(file){{
    if(!file) return;
    if(!/\\.epub$/i.test(file.name)){{
      chosen.textContent = '{js_str(t(lang, "upload_invalid_type"))}';
      input.value = '';
      return false;
    }}
    if(file.size > MAX){{
      chosen.textContent = '{js_str(t(lang, "upload_too_large"))}';
      input.value = '';
      return false;
    }}
    chosen.textContent = file.name + ' (' + (file.size/1024/1024).toFixed(2) + ' MB)';
    return true;
  }}
  input.addEventListener('change', () => setName(input.files[0]));
  dz.addEventListener('dragover', e => {{ e.preventDefault(); dz.classList.add('over'); }});
  dz.addEventListener('dragleave', () => dz.classList.remove('over'));
  dz.addEventListener('drop', e => {{
    e.preventDefault(); dz.classList.remove('over');
    if(!e.dataTransfer.files.length) return;
    input.files = e.dataTransfer.files;
    setName(input.files[0]);
  }});
  form.addEventListener('submit', () => {{
    if(!input.files.length) return;
    form.querySelector('button[type=submit]').disabled = true;
    loader.classList.remove('hidden');
  }});
}})();
</script>
"""
    return layout(lang=lang, title=f"{t(lang, 'brand_name')} — {t(lang, 'brand_tagline')}",
                  body=body, active_nav='home', canonical_path='/')


def js_str(s: str) -> str:
    """Escape a Python string for safe interpolation inside a single-quoted JS literal."""
    return (
        s.replace('\\', '\\\\')
         .replace("'", "\\'")
         .replace('\n', '\\n')
         .replace('\r', '')
         .replace('</', '<\\/')
    )


# ── Report page ──────────────────────────────────────────────────────────────

def render_report(lang: str, session: dict, *, for_download: bool = False) -> str:
    report = session['report']
    validation = session['validation']
    meta = session['meta']
    indic = meta.get('indicators') or compute_indicators(report, validation)

    body_parts: list[str] = []

    # Heading
    head_actions = ''
    if not for_download:
        head_actions = f"""
        <div class="report-actions no-print">
          <a class="btn btn-secondary" href="/report/download">
            <i data-lucide="download" aria-hidden="true"></i>
            {E(t(lang, 'report_download_html'))}
          </a>
          <button type="button" class="btn btn-secondary" onclick="window.print()">
            <i data-lucide="printer" aria-hidden="true"></i>
            {E(t(lang, 'report_print'))}
          </button>
          <a class="btn btn-ghost" href="/">{E(t(lang, 'report_back'))}</a>
        </div>
        """

    body_parts.append(f"""
<header class="report-head">
  <div>
    <h1>{E(t(lang, 'report_h1'))}</h1>
    <p class="report-meta">
      <strong>{E(t(lang, 'report_filename'))}:</strong> {E(meta.get('filename', '—'))}
      &nbsp;·&nbsp;
      <strong>{E(t(lang, 'report_analyzed_at'))}:</strong> {E(meta.get('created_at', _now_iso()))}
    </p>
  </div>
  {head_actions}
</header>
""")

    # Indicators
    body_parts.append(_render_indicators(lang, indic, validation))

    # Section A — current state
    body_parts.append(_render_section_a(lang, report, validation))

    # Section B — issues
    body_parts.append(_render_section_b(lang, report))

    # CTA AccesPub
    body_parts.append(_render_cta(lang, report, indic))

    body = '\n'.join(body_parts)
    return layout(
        lang=lang,
        title=f"{t(lang, 'report_h1')} — {meta.get('filename', '')}",
        body=body,
        inline_assets=for_download,
        canonical_path='/report',
        noindex=True,  # Per-session report — never index
    )


def _render_indicators(lang: str, indic: dict, validation: dict) -> str:
    """Three traffic-light cards."""
    def card(key: str, status: str, msg_key_ok: str, msg_key_warn: str,
             msg_key_err: str, **fmt) -> str:
        if status == 'ok':
            label = t(lang, 'indic_status_ok')
            msg = t(lang, msg_key_ok, **fmt)
            cls = 'ok'
        elif status == 'warn':
            label = t(lang, 'indic_status_warn')
            msg = t(lang, msg_key_warn, **fmt)
            cls = 'warn'
        else:
            label = t(lang, 'indic_status_error')
            msg = t(lang, msg_key_err, **fmt)
            cls = 'error'
        title = t(lang, 'indic_' + key)
        return f"""
        <article class="indicator indicator-{cls}">
          <div class="indicator-dot" aria-hidden="true"></div>
          <h3>{E(title)}</h3>
          <p class="indicator-status">{E(label)}</p>
          <p class="indicator-msg">{E(msg)}</p>
        </article>
        """

    epc_card_status = indic['epubcheck']
    if epc_card_status == 'unavailable':
        epc_html = f"""
        <article class="indicator indicator-unknown">
          <div class="indicator-dot" aria-hidden="true"></div>
          <h3>{E(t(lang, 'indic_epubcheck'))}</h3>
          <p class="indicator-status">—</p>
          <p class="indicator-msg">{E(t(lang, 'epubcheck_unavailable'))}</p>
        </article>
        """
    else:
        epc_html = card(
            'epubcheck', epc_card_status,
            'indic_epubcheck_ok', 'indic_epubcheck_warn', 'indic_epubcheck_error',
            n=validation.get('warnings', 0),
            errors=validation.get('errors', 0),
            warnings=validation.get('warnings', 0),
        )

    return f"""
<section class="indicators" aria-labelledby="indic-h2">
  <h2 id="indic-h2" class="visually-hidden">{E(t(lang, 'indic_title'))}</h2>
  {card('eaa', indic['eaa'],
        'indic_eaa_ok', 'indic_eaa_warn', 'indic_eaa_error')}
  {card('wcag', indic['wcag'],
        'indic_wcag_ok', 'indic_wcag_warn', 'indic_wcag_error')}
  {epc_html}
</section>
"""


def _render_section_a(lang: str, report: dict, validation: dict) -> str:
    rows = [
        (t(lang, 'meta_version'), report.get('epub_version') or t(lang, 'meta_unknown')),
        (t(lang, 'meta_language'), report.get('language') or t(lang, 'meta_unknown')),
        (t(lang, 'meta_title'),    report.get('title') or t(lang, 'meta_unknown')),
        (t(lang, 'meta_total_docs'),  str(report.get('total_documents', 0))),
        (t(lang, 'meta_total_images'),str(report.get('total_images', 0))),
    ]
    rows_html = ''.join(
        f'<tr><th scope="row">{E(k)}</th><td>{E(v)}</td></tr>' for k, v in rows
    )

    epc_html = _render_epubcheck_block(lang, validation)

    return f"""
<section class="section section-a">
  <h2>{E(t(lang, 'sec_a_h2'))}</h2>
  <p>{E(t(lang, 'sec_a_intro'))}</p>
  <table class="meta-table">
    <tbody>{rows_html}</tbody>
  </table>
  {epc_html}
</section>
"""


def _render_epubcheck_block(lang: str, validation: dict) -> str:
    if not validation.get('available'):
        return f'<p class="muted">{E(t(lang, "epubcheck_unavailable"))}</p>'

    errors = validation.get('errors', 0)
    warnings = validation.get('warnings', 0)
    fatals = validation.get('fatals', 0)
    summary = t(lang, 'epubcheck_summary',
                errors=errors, warnings=warnings, fatals=fatals)

    if not validation.get('messages'):
        return f"""
        <h3>{E(t(lang, 'epubcheck_h3'))}</h3>
        <p class="success">{E(t(lang, 'epubcheck_ok'))}</p>
        """

    sev_label = {
        'FATAL':   t(lang, 'sev_fatal'),
        'ERROR':   t(lang, 'sev_error'),
        'WARNING': t(lang, 'sev_warning'),
        'INFO':    t(lang, 'sev_info'),
        'USAGE':   t(lang, 'sev_usage'),
    }

    rows = []
    # Sort: fatal > error > warning > info > usage
    order = {'FATAL': 0, 'ERROR': 1, 'WARNING': 2, 'INFO': 3, 'USAGE': 4}
    for m in sorted(validation['messages'],
                    key=lambda x: order.get(x.get('severity', 'INFO'), 9)):
        sev = m.get('severity', 'INFO')
        rows.append(
            f'<tr class="sev-{sev.lower()}">'
            f'<td><span class="sev-pill sev-{sev.lower()}">'
            f'{E(sev_label.get(sev, sev))}</span></td>'
            f'<td><code>{E(m.get("id", ""))}</code></td>'
            f'<td><code>{E(m.get("location", ""))}</code></td>'
            f'<td>{E(m.get("message", ""))}</td>'
            '</tr>'
        )

    # The <details> is left collapsed by default in the live view; the
    # @media print stylesheet forces every <details> open so the printed
    # report includes the full EPUBCheck table.
    return f"""
<h3>{E(t(lang, 'epubcheck_h3'))}</h3>
<details class="epubcheck-details epubcheck-table">
  <summary>
    <strong>{E(summary)}</strong>
  </summary>
  <table class="issues-table">
    <thead>
      <tr>
        <th>{E(t(lang, 'epubcheck_col_severity'))}</th>
        <th>{E(t(lang, 'epubcheck_col_id'))}</th>
        <th>{E(t(lang, 'epubcheck_col_location'))}</th>
        <th>{E(t(lang, 'epubcheck_col_message'))}</th>
      </tr>
    </thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</details>
"""


def _render_section_b(lang: str, report: dict) -> str:
    issues = report.get('issues') or []
    auto_count = sum(1 for i in issues if i.get('auto_fixable'))
    manual_count = len(issues) - auto_count

    # Manual review notes about images / tables / langs
    review_html_parts: list[str] = []
    n_imgs = len(report.get('images_for_review') or [])
    if n_imgs:
        review_html_parts.append(
            f'<aside class="callout"><h3>{E(t(lang, "review_images_h3"))}</h3>'
            f'<p>{E(t(lang, "review_images_body", n=n_imgs))}</p></aside>'
        )
    n_tbls = len(report.get('tables_for_review') or [])
    if n_tbls:
        review_html_parts.append(
            f'<aside class="callout"><h3>{E(t(lang, "review_tables_h3"))}</h3>'
            f'<p>{E(t(lang, "review_tables_body", n=n_tbls))}</p></aside>'
        )
    n_lang = len(report.get('lang_items') or [])
    if n_lang:
        review_html_parts.append(
            f'<aside class="callout"><h3>{E(t(lang, "review_lang_h3"))}</h3>'
            f'<p>{E(t(lang, "review_lang_body", n=n_lang))}</p></aside>'
        )

    if not issues and not review_html_parts:
        return f"""
<section class="section section-b">
  <h2>{E(t(lang, 'sec_b_h2'))}</h2>
  <p class="success">{E(t(lang, 'sec_b_no_issues'))}</p>
</section>
"""

    summary = t(lang, 'sec_b_summary',
                total=len(issues), auto=auto_count, manual=manual_count)

    # Sort issues by severity, then type
    sev_order = {'critical': 0, 'serious': 1, 'moderate': 2, 'minor': 3}
    issues_sorted = sorted(
        issues,
        key=lambda i: (sev_order.get(i.get('severity', 'minor'), 9),
                       i.get('type', ''),
                       i.get('location', '')),
    )

    rows = []
    for i in issues_sorted:
        sev = i.get('severity', 'minor')
        typ = i.get('type', 'other')
        sev_label = t(lang, 'severity_' + sev) if f'severity_{sev}' in _T_keys() else sev
        type_label = t(lang, 'type_' + typ) if f'type_{typ}' in _T_keys() else typ
        fix_text = t(lang, 'fix_auto') if i.get('auto_fixable') else t(lang, 'fix_manual')
        fix_cls = 'fix-auto' if i.get('auto_fixable') else 'fix-manual'
        description = translate_issue(lang, i)
        rows.append(
            f'<tr class="sev-{sev}">'
            f'<td><span class="sev-pill sev-{sev}">{E(sev_label)}</span></td>'
            f'<td><span class="type-pill">{E(type_label)}</span></td>'
            f'<td><code>{E(i.get("location", ""))}</code></td>'
            f'<td>{E(description)}</td>'
            f'<td><span class="{fix_cls}">{E(fix_text)}</span></td>'
            '</tr>'
        )

    table_html = ''
    if rows:
        table_html = f"""
<table class="issues-table">
  <thead>
    <tr>
      <th>{E(t(lang, 'issue_col_severity'))}</th>
      <th>{E(t(lang, 'issue_col_type'))}</th>
      <th>{E(t(lang, 'issue_col_location'))}</th>
      <th>{E(t(lang, 'issue_col_description'))}</th>
      <th>{E(t(lang, 'issue_col_fix'))}</th>
    </tr>
  </thead>
  <tbody>{''.join(rows)}</tbody>
</table>
"""

    return f"""
<section class="section section-b">
  <h2>{E(t(lang, 'sec_b_h2'))}</h2>
  <p>{E(t(lang, 'sec_b_intro'))}</p>
  <p class="summary"><strong>{E(summary)}</strong></p>
  {''.join(review_html_parts)}
  {table_html}
</section>
"""


from functools import lru_cache


@lru_cache(maxsize=1)
def _T_keys() -> frozenset[str]:
    """Memoised set of i18n keys available in the default language."""
    from dashboard.i18n import _T  # type: ignore[attr-defined]
    return frozenset(_T.get('en', {}).keys())


# ─────────────────────────────────────────────────────────────────────────────
#  Issue description translation
# ─────────────────────────────────────────────────────────────────────────────
# The engine emits issue descriptions in two ways:
#   1. With a `description_key` + `description_args` — i18n keys defined in
#      i18n.py (issue_desc_*).
#   2. As a plain English string in `description` — for those, we run a list
#      of regex patterns and translate via `issue_pat_*` keys.
# Anything that doesn't match either case falls through unchanged.

_ISSUE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r'^Missing required accessibility metadata:\s*(?P<prop>.+)$'),
     'issue_pat_missing_a11y_meta'),
    (re.compile(r'^Image missing alt attribute:\s*(?P<src>.+)$'),
     'issue_pat_img_no_alt'),
    (re.compile(r'^Cover image has no alt text:\s*(?P<href>.+)$'),
     'issue_pat_cover_no_alt'),
    (re.compile(
        r'^El documento est[aá] en formato EPUB\s*(?P<version>[\d.]+).*$',
        re.DOTALL,
    ),
     'issue_pat_epub2_to_3'),
    (re.compile(r'^The document is in EPUB\s*(?P<version>[\d.]+).*$',
                re.DOTALL),
     'issue_pat_epub2_to_3'),
    (re.compile(r'^Document contains inline style attributes\..*$', re.DOTALL),
     'issue_pat_inline_styles'),
    (re.compile(
        r'^Decorative image will be marked with alt="" \(auto-fix\):\s*(?P<src>.+)$'
    ),
     'issue_pat_decorative_alt'),
    (re.compile(
        r'^Image has alt="" — may be auto-generated.*?:\s*(?P<src>.+)$',
        re.DOTALL,
    ),
     'issue_pat_empty_alt'),
    (re.compile(
        r'^Image has a generic/placeholder alt text \("(?P<alt>[^"]*)"\)\s*'
        r'.*?:\s*(?P<src>.+)$',
        re.DOTALL,
    ),
     'issue_pat_generic_alt'),
    (re.compile(
        r'^Element with epub:type="(?P<etype>[^"]+)" is missing matching ARIA '
        r'role="(?P<role>[^"]+)"$'
    ),
     'issue_pat_epub_type_role'),
    (re.compile(
        r'^<nav epub:type="(?P<etype>[^"]+)"> has no aria-label.*$', re.DOTALL,
    ),
     'issue_pat_nav_no_label'),
    (re.compile(
        r'^NCX-001:\s*NCX identifier \("(?P<ncx>[^"]*)"\) does not match OPF '
        r'unique identifier \("(?P<opf>[^"]*)"\)\..*$',
        re.DOTALL,
    ),
     'issue_pat_ncx_uid'),
    (re.compile(
        r'^Insufficient color contrast in selector\s*"(?P<selector>[^"]+)":\s*'
        r'(?P<fg>\S+)\s+on\s+(?P<bg>\S+)\s*—\s*ratio\s*(?P<ratio>[\d.]+).*$',
        re.DOTALL,
    ),
     'issue_pat_contrast'),
]


def translate_issue(lang: str, issue: dict) -> str:
    """Return the translated description for a single issue dict.

    Resolution order:
      1. `description_key` (engine-side i18n key) — applied with description_args
      2. Pattern matching on `description` — regexes mapped to issue_pat_* keys
      3. Fall back to the raw description (typically English) unchanged
    """
    key = (issue.get('description_key') or '').strip()
    if key and key in _T_keys():
        args = issue.get('description_args') or {}
        return t(lang, key, **args)

    desc = (issue.get('description') or '').strip()
    if not desc:
        return ''
    for pattern, pkey in _ISSUE_PATTERNS:
        m = pattern.match(desc)
        if m:
            return t(lang, pkey, **m.groupdict())
    return desc


def _render_cta(lang: str, report: dict, indic: dict) -> str:
    version = (report.get('epub_version') or '').strip()
    is_epub2 = version.startswith('2')
    n_auto = sum(1 for i in (report.get('issues') or []) if i.get('auto_fixable'))
    is_clean = (
        not is_epub2
        and indic['eaa'] == 'ok' and indic['wcag'] == 'ok'
        and (indic['epubcheck'] in ('ok', 'unavailable'))
        and not indic.get('has_manual_review')
        and n_auto == 0
    )

    if is_clean:
        title = t(lang, 'cta_clean_title')
        body = t(lang, 'cta_clean_body')
    elif is_epub2:
        title = t(lang, 'cta_epub2_title')
        body = t(lang, 'cta_epub2_body')
    else:
        title = t(lang, 'cta_epub3_title', n=n_auto)
        body = t(lang, 'cta_epub3_body')

    return f"""
<section class="cta">
  <h2>{E(t(lang, 'cta_h2'))}</h2>
  <div class="cta-card">
    <h3>{E(title)}</h3>
    <p>{E(body)}</p>
    <a class="btn btn-primary btn-lg" href="{E(t(lang, 'cta_url'))}" rel="external">
      {E(t(lang, 'cta_button'))} →
    </a>
  </div>
</section>
"""


# ── Help / Legal pages ───────────────────────────────────────────────────────

def render_help(lang: str) -> str:
    items = [(f'help_q{i}', f'help_a{i}') for i in range(1, 7)]
    rows = ''.join(
        f'<details class="faq-item"><summary><strong>{E(t(lang, q))}</strong></summary>'
        f'<p>{E(t(lang, a))}</p></details>'
        for q, a in items
    )
    body = f"""
<header class="page-head"><h1>{E(t(lang, 'help_h1'))}</h1></header>
<section class="faq">{rows}</section>
"""
    return layout(lang=lang, title=t(lang, 'help_h1'), body=body,
                  active_nav='help', canonical_path='/help')


def render_legal(lang: str) -> str:
    sections = [
        ('legal_owner_h2',     'legal_owner_body'),
        ('legal_purpose_h2',   'legal_purpose_body'),
        ('legal_data_h2',      'legal_data_body'),
        ('legal_files_h2',     'legal_files_body'),
        ('legal_liability_h2', 'legal_liability_body'),
    ]
    body = f'<header class="page-head"><h1>{E(t(lang, "legal_h1"))}</h1></header>'
    body += '<section class="legal">'
    for h, b in sections:
        # Preserve embedded newlines in the source string as visible line
        # breaks. This is what the owner section uses to list NIF, address
        # and contact email on separate lines.
        text = E(t(lang, b)).replace('\n', '<br>')
        body += f'<h2>{E(t(lang, h))}</h2><p>{text}</p>'
    body += '</section>'
    return layout(lang=lang, title=t(lang, 'legal_h1'), body=body,
                  active_nav='legal', canonical_path='/legal')


# ─────────────────────────────────────────────────────────────────────────────
#  HTTP handler
# ─────────────────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    server_version = 'AnalizePub/0.1'

    # ── Logging ──────────────────────────────────────────────────────────
    def log_message(self, fmt: str, *args: Any) -> None:
        log.info('%s - %s', self.address_string(), fmt % args)

    # ── Cookie helpers ───────────────────────────────────────────────────
    def _cookies(self) -> SimpleCookie:
        c = SimpleCookie()
        raw = self.headers.get('Cookie')
        if raw:
            c.load(raw)
        return c

    def _get_lang(self) -> str:
        cookies = self._cookies()
        lang_c = cookies.get(COOKIE_LANG)
        accept = self.headers.get('Accept-Language', '')
        return lang_from_cookie_or_header(
            lang_c.value if lang_c else None, accept
        )

    def _get_session_id(self) -> str | None:
        cookies = self._cookies()
        c = cookies.get(COOKIE_SESSION)
        return c.value if c else None

    # ── Response helpers ─────────────────────────────────────────────────
    def _send_html(self, html_text: str, *, status: int = 200,
                   extra_headers: dict[str, str] | None = None) -> None:
        body = html_text.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_redirect(self, location: str, *,
                       set_cookies: dict[str, tuple[str, int]] | None = None) -> None:
        self.send_response(303)
        self.send_header('Location', location)
        if set_cookies:
            for name, (value, max_age) in set_cookies.items():
                self.send_header(
                    'Set-Cookie',
                    f'{name}={value}; Path=/; Max-Age={max_age}; '
                    f'HttpOnly; SameSite=Lax'
                )
        self.send_header('Content-Length', '0')
        self.end_headers()

    def _send_text(self, text: str, *, status: int = 200,
                   content_type: str = 'text/plain; charset=utf-8') -> None:
        body = text.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data: bytes, *, content_type: str,
                    filename: str | None = None) -> None:
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        if filename:
            self.send_header(
                'Content-Disposition',
                f'attachment; filename="{filename}"',
            )
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _send_404(self, lang: str) -> None:
        self._send_html(
            layout(lang=lang, title=t(lang, 'err_404'),
                   body=f'<h1>404</h1><p>{E(t(lang, "err_404"))}</p>'),
            status=404,
        )

    def _send_500(self, lang: str, detail: str = '') -> None:
        msg = t(lang, 'err_500')
        body = f'<h1>500</h1><p>{E(msg)}</p>'
        if detail:
            body += f'<pre class="error-trace">{E(detail)}</pre>'
        self._send_html(layout(lang=lang, title=msg, body=body), status=500)

    # ── GET routes ───────────────────────────────────────────────────────
    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        try:
            parsed = urlparse(self.path)
            route = parsed.path
            lang = self._get_lang()

            if route == '/':
                return self._send_html(render_upload(lang))

            if route == '/help':
                return self._send_html(render_help(lang))

            if route == '/legal':
                return self._send_html(render_legal(lang))

            if route == '/set-lang':
                qs = parse_qs(parsed.query)
                new_lang = (qs.get('lang') or [DEFAULT_LANG])[0]
                if new_lang not in SUPPORTED_LANGS:
                    new_lang = DEFAULT_LANG
                # A language change always returns the user to a clean home
                # page. Any active analysis session is dropped — the report
                # is locked to the language it was rendered in, so showing
                # a half-translated page would be worse than a fresh start.
                sid = self._get_session_id()
                if sid:
                    sessions.delete(sid)
                return self._send_redirect(
                    '/',
                    set_cookies={
                        COOKIE_LANG:    (new_lang, 60 * 60 * 24 * 365),
                        COOKIE_SESSION: ('', 0),
                    },
                )

            if route == '/report':
                return self._handle_report(lang, mode='view')

            if route == '/report/download':
                return self._handle_report(lang, mode='download_html')

            if route == '/robots.txt':
                return self._send_text(_render_robots_txt(),
                                       content_type='text/plain; charset=utf-8')

            if route == '/sitemap.xml':
                return self._send_text(_render_sitemap_xml(),
                                       content_type='application/xml; charset=utf-8')

            if route.startswith('/static/'):
                return self._serve_static(route[len('/static/'):])

            return self._send_404(lang)

        except Exception as exc:  # pragma: no cover - last-resort handler
            log.exception('GET handler error: %s', exc)
            try:
                self._send_500(self._get_lang(), str(exc))
            except Exception:
                pass

    # ── POST routes ──────────────────────────────────────────────────────
    def do_POST(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            route = parsed.path
            lang = self._get_lang()

            if route == '/upload':
                return self._handle_upload(lang)

            if route == '/reset':
                sid = self._get_session_id()
                if sid:
                    sessions.delete(sid)
                return self._send_redirect(
                    '/',
                    set_cookies={COOKIE_SESSION: ('', 0)},
                )

            return self._send_404(lang)

        except Exception as exc:  # pragma: no cover
            log.exception('POST handler error: %s', exc)
            try:
                self._send_500(self._get_lang(), str(exc))
            except Exception:
                pass

    # ── Static files ─────────────────────────────────────────────────────
    def _serve_static(self, rel: str) -> None:
        # Defensive: reject path traversal
        rel = rel.lstrip('/').replace('..', '')
        path = (STATIC_DIR / rel).resolve()
        if not str(path).startswith(str(STATIC_DIR.resolve())) or not path.is_file():
            return self._send_404(self._get_lang())
        ctype, _ = mimetypes.guess_type(str(path))
        ctype = ctype or 'application/octet-stream'
        try:
            data = path.read_bytes()
        except OSError:
            return self._send_404(self._get_lang())
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'public, max-age=300')
        self.end_headers()
        self.wfile.write(data)

    # ── Report rendering / downloads ─────────────────────────────────────
    def _handle_report(self, lang: str, *, mode: str) -> None:
        sid = self._get_session_id()
        sess = sessions.load(sid) if sid else None
        if not sess:
            body = f"""
<header class="page-head"><h1>{E(t(lang, 'report_h1'))}</h1></header>
<div class="alert alert-warn">{E(t(lang, 'report_session_expired'))}</div>
<a href="/" class="btn btn-primary">{E(t(lang, 'report_back'))}</a>
"""
            return self._send_html(
                layout(lang=lang, title=t(lang, 'report_h1'), body=body),
                status=410,
            )

        if mode == 'view':
            return self._send_html(render_report(lang, sess))

        if mode == 'download_html':
            html_text = render_report(lang, sess, for_download=True)
            filename = _safe_filename(sess['meta'].get('filename', 'report'),
                                      ext='-analizepub.html')
            return self._send_bytes(
                html_text.encode('utf-8'),
                content_type='text/html; charset=utf-8',
                filename=filename,
            )

        return self._send_404(lang)

    # ── Upload handler ───────────────────────────────────────────────────
    def _handle_upload(self, lang: str) -> None:
        ctype = self.headers.get('Content-Type', '')
        m = re.match(r'multipart/form-data;\s*boundary=(.+)', ctype, re.IGNORECASE)
        if not m:
            return self._send_html(
                render_upload(lang, error=t(lang, 'err_no_file')), status=400,
            )
        boundary = m.group(1).strip().strip('"').encode('utf-8')

        clen = int(self.headers.get('Content-Length') or 0)
        if clen <= 0:
            return self._send_html(
                render_upload(lang, error=t(lang, 'err_no_file')), status=400,
            )
        if clen > MAX_UPLOAD_BYTES + 4096:  # small overhead for boundary
            return self._send_html(
                render_upload(lang, error=t(lang, 'err_too_large')), status=413,
            )

        try:
            filename, data = parse_multipart(
                self.rfile, boundary,
                content_length=clen,
                max_bytes=MAX_UPLOAD_BYTES + 8192,
            )
        except MultipartError:
            return self._send_html(
                render_upload(lang, error=t(lang, 'err_too_large')), status=413,
            )
        if not filename or not data:
            return self._send_html(
                render_upload(lang, error=t(lang, 'err_no_file')), status=400,
            )
        if not filename.lower().endswith('.epub'):
            return self._send_html(
                render_upload(lang, error=t(lang, 'err_invalid_epub')), status=400,
            )
        if len(data) > MAX_UPLOAD_BYTES:
            return self._send_html(
                render_upload(lang, error=t(lang, 'err_too_large')), status=413,
            )

        # Write to a temporary file and analyse
        with tempfile.TemporaryDirectory(prefix='analizepub_') as tmp:
            epub_path = os.path.join(tmp, _safe_filename(filename, ext='.epub'))
            with open(epub_path, 'wb') as fh:
                fh.write(data)

            # Quick sanity checks
            if not zipfile.is_zipfile(epub_path):
                return self._send_html(
                    render_upload(lang, error=t(lang, 'err_invalid_epub')),
                    status=400,
                )
            if is_fixed_layout(epub_path):
                return self._send_html(
                    render_upload(lang, error=t(lang, 'err_fixed_layout')),
                    status=400,
                )

            # Run analyser
            try:
                analyzer = EPUBAnalyzer(epub_path)
                report_obj: AnalysisReport = analyzer.analyze()
                report_dict = report_obj.to_dict()
            except Exception as exc:
                log.exception('Analyser error: %s', exc)
                return self._send_html(
                    render_upload(
                        lang,
                        error=t(lang, 'err_analysis_failed', detail=str(exc)),
                    ),
                    status=500,
                )

            # Run EPUBCheck (best effort)
            validation = run_epubcheck(epub_path)

        # Compute indicators and persist
        indic = compute_indicators(report_dict, validation)
        sid = sessions.new_id()
        sessions.cleanup_expired()
        sessions.save(
            sid,
            report=report_dict,
            validation=validation,
            meta={
                'filename': filename,
                'created_at': _now_iso(),
                'indicators': indic,
            },
        )

        return self._send_redirect(
            '/report',
            set_cookies={COOKIE_SESSION: (sid, SESSION_TTL_SECONDS)},
        )


def _safe_filename(name: str, *, ext: str) -> str:
    """Trim path separators and non-printable chars; suffix with `ext`."""
    base = os.path.basename(name).strip()
    base = re.sub(r'[^\w\.\- ]+', '_', base)[:120].strip() or 'file'
    if not base.lower().endswith(ext.lower()):
        # Replace existing extension
        stem = re.sub(r'\.[A-Za-z0-9]{1,5}$', '', base)
        base = stem + ext
    return base


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

def _startup_checks() -> None:
    log.info('Sessions dir: %s', SESSIONS_DIR)
    log.info('Max upload  : %d bytes (%.1f MB)',
             MAX_UPLOAD_BYTES, MAX_UPLOAD_BYTES / 1024 / 1024)
    log.info('Session TTL : %d seconds', SESSION_TTL_SECONDS)
    log.info('EPUBCheck   : %s', 'available' if EPUBCHECK_IMPORT_OK else 'NOT installed')
    n = sessions.cleanup_expired()
    if n:
        log.info('Cleaned up %d expired session(s) at boot', n)


class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
    """Same as ThreadingHTTPServer but with SO_REUSEADDR enabled so that a
    quick restart does not fail with `Address already in use` while a socket
    from the previous run is still in TIME_WAIT."""
    allow_reuse_address = True
    daemon_threads = True


def serve(host: str = HOST, port: int = PORT) -> None:
    _startup_checks()
    try:
        server = _ReusableThreadingHTTPServer((host, port), Handler)
    except OSError as exc:
        # errno 48 = macOS, 98 = Linux  (EADDRINUSE)
        if exc.errno in (48, 98):
            log.error(
                'Port %d on %s is already in use.\n'
                '  → Kill the previous server:  lsof -ti :%d | xargs kill\n'
                '  → Or use a different port:   PORT=8090 python -m dashboard.app',
                port, host, port,
            )
            sys.exit(1)
        raise

    log.info('AnalizePub listening on http://%s:%d', host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info('Shutting down…')
        server.server_close()


if __name__ == '__main__':
    serve()
