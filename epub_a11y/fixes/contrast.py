"""
contrast.py — WCAG 2.1 color contrast checking and fixing for EPUB CSS files.

WCAG 2.1 AA requirements:
  - Normal text:  contrast ratio ≥ 4.5 : 1
  - Large text:   contrast ratio ≥ 3.0 : 1
    (large = ≥ 18pt / 24px, or ≥ 14pt / 18.67px AND bold)

Strategy:
  1. Parse every CSS rule that sets `color` (foreground).
  2. Look for a `background-color` in the same rule or inherited defaults.
  3. Compute the contrast ratio.
  4. If below threshold, adjust the foreground color by binary-searching its
     HSL lightness (darken on light bg, lighten on dark bg) until the ratio
     meets the requirement.
  5. Rewrite the CSS file with the adjusted color values.
"""

from __future__ import annotations

import colorsys
import math
import os
import re
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Named CSS colors (CSS Color Level 4 / CSS 2.1 subset used in EPUBs)
# ---------------------------------------------------------------------------

_NAMED_COLORS: Dict[str, Tuple[int, int, int]] = {
    'aliceblue': (240, 248, 255), 'antiquewhite': (250, 235, 215),
    'aqua': (0, 255, 255), 'aquamarine': (127, 255, 212),
    'azure': (240, 255, 255), 'beige': (245, 245, 220),
    'bisque': (255, 228, 196), 'black': (0, 0, 0),
    'blanchedalmond': (255, 235, 205), 'blue': (0, 0, 255),
    'blueviolet': (138, 43, 226), 'brown': (165, 42, 42),
    'burlywood': (222, 184, 135), 'cadetblue': (95, 158, 160),
    'chartreuse': (127, 255, 0), 'chocolate': (210, 105, 30),
    'coral': (255, 127, 80), 'cornflowerblue': (100, 149, 237),
    'cornsilk': (255, 248, 220), 'crimson': (220, 20, 60),
    'cyan': (0, 255, 255), 'darkblue': (0, 0, 139),
    'darkcyan': (0, 139, 139), 'darkgoldenrod': (184, 134, 11),
    'darkgray': (169, 169, 169), 'darkgreen': (0, 100, 0),
    'darkgrey': (169, 169, 169), 'darkkhaki': (189, 183, 107),
    'darkmagenta': (139, 0, 139), 'darkolivegreen': (85, 107, 47),
    'darkorange': (255, 140, 0), 'darkorchid': (153, 50, 204),
    'darkred': (139, 0, 0), 'darksalmon': (233, 150, 122),
    'darkseagreen': (143, 188, 143), 'darkslateblue': (72, 61, 139),
    'darkslategray': (47, 79, 79), 'darkslategrey': (47, 79, 79),
    'darkturquoise': (0, 206, 209), 'darkviolet': (148, 0, 211),
    'deeppink': (255, 20, 147), 'deepskyblue': (0, 191, 255),
    'dimgray': (105, 105, 105), 'dimgrey': (105, 105, 105),
    'dodgerblue': (30, 144, 255), 'firebrick': (178, 34, 34),
    'floralwhite': (255, 250, 240), 'forestgreen': (34, 139, 34),
    'fuchsia': (255, 0, 255), 'gainsboro': (220, 220, 220),
    'ghostwhite': (248, 248, 255), 'gold': (255, 215, 0),
    'goldenrod': (218, 165, 32), 'gray': (128, 128, 128),
    'green': (0, 128, 0), 'greenyellow': (173, 255, 47),
    'grey': (128, 128, 128), 'honeydew': (240, 255, 240),
    'hotpink': (255, 105, 180), 'indianred': (205, 92, 92),
    'indigo': (75, 0, 130), 'ivory': (255, 255, 240),
    'khaki': (240, 230, 140), 'lavender': (230, 230, 250),
    'lavenderblush': (255, 240, 245), 'lawngreen': (124, 252, 0),
    'lemonchiffon': (255, 250, 205), 'lightblue': (173, 216, 230),
    'lightcoral': (240, 128, 128), 'lightcyan': (224, 255, 255),
    'lightgoldenrodyellow': (250, 250, 210), 'lightgray': (211, 211, 211),
    'lightgreen': (144, 238, 144), 'lightgrey': (211, 211, 211),
    'lightpink': (255, 182, 193), 'lightsalmon': (255, 160, 122),
    'lightseagreen': (32, 178, 170), 'lightskyblue': (135, 206, 250),
    'lightslategray': (119, 136, 153), 'lightslategrey': (119, 136, 153),
    'lightsteelblue': (176, 196, 222), 'lightyellow': (255, 255, 224),
    'lime': (0, 255, 0), 'limegreen': (50, 205, 50),
    'linen': (250, 240, 230), 'magenta': (255, 0, 255),
    'maroon': (128, 0, 0), 'mediumaquamarine': (102, 205, 170),
    'mediumblue': (0, 0, 205), 'mediumorchid': (186, 85, 211),
    'mediumpurple': (147, 112, 219), 'mediumseagreen': (60, 179, 113),
    'mediumslateblue': (123, 104, 238), 'mediumspringgreen': (0, 250, 154),
    'mediumturquoise': (72, 209, 204), 'mediumvioletred': (199, 21, 133),
    'midnightblue': (25, 25, 112), 'mintcream': (245, 255, 250),
    'mistyrose': (255, 228, 225), 'moccasin': (255, 228, 181),
    'navajowhite': (255, 222, 173), 'navy': (0, 0, 128),
    'oldlace': (253, 245, 230), 'olive': (128, 128, 0),
    'olivedrab': (107, 142, 35), 'orange': (255, 165, 0),
    'orangered': (255, 69, 0), 'orchid': (218, 112, 214),
    'palegoldenrod': (238, 232, 170), 'palegreen': (152, 251, 152),
    'paleturquoise': (175, 238, 238), 'palevioletred': (219, 112, 147),
    'papayawhip': (255, 239, 213), 'peachpuff': (255, 218, 185),
    'peru': (205, 133, 63), 'pink': (255, 192, 203),
    'plum': (221, 160, 221), 'powderblue': (176, 224, 230),
    'purple': (128, 0, 128), 'rebeccapurple': (102, 51, 153),
    'red': (255, 0, 0), 'rosybrown': (188, 143, 143),
    'royalblue': (65, 105, 225), 'saddlebrown': (139, 69, 19),
    'salmon': (250, 128, 114), 'sandybrown': (244, 164, 96),
    'seagreen': (46, 139, 87), 'seashell': (255, 245, 238),
    'sienna': (160, 82, 45), 'silver': (192, 192, 192),
    'skyblue': (135, 206, 235), 'slateblue': (106, 90, 205),
    'slategray': (112, 128, 144), 'slategrey': (112, 128, 144),
    'snow': (255, 250, 250), 'springgreen': (0, 255, 127),
    'steelblue': (70, 130, 180), 'tan': (210, 180, 140),
    'teal': (0, 128, 128), 'thistle': (216, 191, 216),
    'tomato': (255, 99, 71), 'transparent': (255, 255, 255),
    'turquoise': (64, 224, 208), 'violet': (238, 130, 238),
    'wheat': (245, 222, 179), 'white': (255, 255, 255),
    'whitesmoke': (245, 245, 245), 'yellow': (255, 255, 0),
    'yellowgreen': (154, 205, 50),
}


# ---------------------------------------------------------------------------
# Color parsing
# ---------------------------------------------------------------------------

def parse_color(s: str) -> Optional[Tuple[int, int, int]]:
    """Parse a CSS color string → (R, G, B) with values 0-255, or None."""
    if not s:
        return None
    s = s.strip().lower()

    # Ignore keywords we can't resolve
    if s in ('currentcolor', 'inherit', 'initial', 'unset', 'revert'):
        return None

    # Named color
    if s in _NAMED_COLORS:
        return _NAMED_COLORS[s]

    # #rgb
    m = re.fullmatch(r'#([0-9a-f])([0-9a-f])([0-9a-f])', s)
    if m:
        return (int(m.group(1) * 2, 16),
                int(m.group(2) * 2, 16),
                int(m.group(3) * 2, 16))

    # #rrggbb or #rrggbbaa
    m = re.fullmatch(r'#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})(?:[0-9a-f]{2})?', s)
    if m:
        return (int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16))

    # rgb(r, g, b) or rgba(r, g, b, a)
    m = re.fullmatch(
        r'rgba?\(\s*(\d+\.?\d*%?)\s*,\s*(\d+\.?\d*%?)\s*,\s*(\d+\.?\d*%?)'
        r'(?:\s*,\s*[\d.]+%?)?\s*\)', s)
    if m:
        def _ch(v: str) -> int:
            if v.endswith('%'):
                return round(float(v[:-1]) * 255 / 100)
            return min(255, max(0, round(float(v))))
        return (_ch(m.group(1)), _ch(m.group(2)), _ch(m.group(3)))

    # hsl(h, s%, l%) or hsla(h, s%, l%, a)
    m = re.fullmatch(
        r'hsla?\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%'
        r'(?:\s*,\s*[\d.]+%?)?\s*\)', s)
    if m:
        h = float(m.group(1)) / 360.0
        sl = float(m.group(2)) / 100.0
        l = float(m.group(3)) / 100.0
        r, g, b = colorsys.hls_to_rgb(h, l, sl)
        return (round(r * 255), round(g * 255), round(b * 255))

    return None


# ---------------------------------------------------------------------------
# Luminance & contrast ratio
# ---------------------------------------------------------------------------

def _linearise(c8: int) -> float:
    """Convert an 8-bit channel value to linear light (WCAG formula)."""
    c = c8 / 255.0
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(r: int, g: int, b: int) -> float:
    """Compute WCAG 2.1 relative luminance for an sRGB color (0-255 inputs)."""
    return (0.2126 * _linearise(r) +
            0.7152 * _linearise(g) +
            0.0722 * _linearise(b))


def contrast_ratio(c1: Tuple[int, int, int],
                   c2: Tuple[int, int, int]) -> float:
    """Return WCAG contrast ratio between two RGB colors."""
    l1 = relative_luminance(*c1)
    l2 = relative_luminance(*c2)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


# ---------------------------------------------------------------------------
# Large-text detection
# ---------------------------------------------------------------------------

def _px_from_font_size(fs: str) -> Optional[float]:
    """Convert a CSS font-size string to px. Returns None if unknown."""
    fs = fs.strip().lower()
    m = re.fullmatch(r'([\d.]+)(px|pt|rem|em)?', fs)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2) or 'px'
    conversions = {'px': 1.0, 'pt': 4 / 3, 'rem': 16.0, 'em': 16.0}
    return val * conversions.get(unit, 1.0)


def is_large_text(props: Dict[str, str]) -> bool:
    """
    Return True if the CSS property set qualifies as 'large text' per WCAG 2.1.
    Large text = ≥ 18pt (24px) regular, or ≥ 14pt (18.67px) bold.
    """
    fs_raw = props.get('font-size', '')
    fw_raw = props.get('font-weight', '').lower()
    bold = fw_raw in ('bold', 'bolder', '700', '800', '900')

    px = _px_from_font_size(fs_raw)
    if px is None:
        return False
    if bold and px >= 18.67:
        return True
    if px >= 24.0:
        return True
    return False


# ---------------------------------------------------------------------------
# Color adjustment (binary search on HSL lightness)
# ---------------------------------------------------------------------------

def _rgb_to_hls(r: int, g: int, b: int) -> Tuple[float, float, float]:
    """Return (H, L, S) in 0-1 range."""
    return colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)


def _hls_to_rgb(h: float, l: float, s: float) -> Tuple[int, int, int]:
    """Return (R, G, B) in 0-255 range."""
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return (round(r * 255), round(g * 255), round(b * 255))


def fix_color_for_contrast(
    fg_rgb: Tuple[int, int, int],
    bg_rgb: Tuple[int, int, int],
    threshold: float = 4.5,
    max_iterations: int = 40,
) -> Tuple[int, int, int]:
    """
    Adjust fg_rgb so that its contrast against bg_rgb meets `threshold`.
    Uses binary search on the HSL lightness axis.

    The direction of adjustment is chosen automatically:
      - If the background is light (L > 0.5), we darken the foreground.
      - If the background is dark (L ≤ 0.5), we lighten the foreground.

    Returns the adjusted (R, G, B), or the extreme (black/white) if no
    intermediate value is sufficient.
    """
    if contrast_ratio(fg_rgb, bg_rgb) >= threshold:
        return fg_rgb  # Already good

    bg_h, bg_l, bg_s = _rgb_to_hls(*bg_rgb)
    fg_h, fg_l, fg_s = _rgb_to_hls(*fg_rgb)

    light_bg = bg_l > 0.5

    # Binary search bounds for foreground lightness
    if light_bg:
        lo, hi = 0.0, fg_l   # darken → search [0, current_L]
    else:
        lo, hi = fg_l, 1.0   # lighten → search [current_L, 1]

    best = fg_rgb
    for _ in range(max_iterations):
        mid = (lo + hi) / 2.0
        candidate = _hls_to_rgb(fg_h, mid, fg_s)
        ratio = contrast_ratio(candidate, bg_rgb)
        if ratio >= threshold:
            best = candidate
            if light_bg:
                lo = mid   # can afford to go a bit lighter (save it, try bigger)
            else:
                hi = mid   # can afford to go a bit darker
        else:
            if light_bg:
                hi = mid   # need to go darker
            else:
                lo = mid   # need to go lighter

        if abs(hi - lo) < 1e-4:
            break

    # If still not passing, fall back to pure black/white
    if contrast_ratio(best, bg_rgb) < threshold:
        best = (0, 0, 0) if light_bg else (255, 255, 255)

    return best


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f'#{r:02x}{g:02x}{b:02x}'


# ---------------------------------------------------------------------------
# CSS text processing
# ---------------------------------------------------------------------------

# Default background assumed when no background-color is specified.
_DEFAULT_BG: Tuple[int, int, int] = (255, 255, 255)  # white

# Property names that carry foreground color
_FG_PROPS = {'color'}
# Property names that carry background color
_BG_PROPS = {'background-color', 'background'}


def _extract_props_from_block(block: str) -> Dict[str, str]:
    """
    Extract CSS property→value pairs from a rule body (content between { }).
    Returns a dict. Values are raw strings (not parsed), with any trailing
    ``!important`` annotation stripped so colour parsers receive clean values.
    """
    props: Dict[str, str] = {}
    for decl in re.split(r';', block):
        decl = decl.strip()
        if ':' not in decl:
            continue
        prop, _, val = decl.partition(':')
        # Strip !important — added by css_consolidator to preserve inline-style
        # precedence; must be removed here so parse_color() can recognise the value.
        clean_val = re.sub(r'\s*!important\s*$', '', val.strip(), flags=re.IGNORECASE)
        props[prop.strip().lower()] = clean_val
    return props


def _build_replacement_decl(prop: str, old_val: str,
                             new_rgb: Tuple[int, int, int]) -> str:
    """Return a CSS declaration string with the new hex color."""
    return f'{prop}: {_rgb_to_hex(*new_rgb)}'


def _collect_all_backgrounds(css_text: str) -> List[Tuple[int, int, int]]:
    """
    Pre-scan a complete CSS text and return every unique, parseable
    background color declared in ANY rule.

    This is used by fix_css_text to avoid "fixing" a foreground color that
    already achieves good contrast against a background declared elsewhere
    in the same stylesheet (e.g. white text designed for a dark parent div).
    """
    bgs: List[Tuple[int, int, int]] = []
    pattern = re.compile(r'[^{}/]+?\{([^{}]*?)\}', re.DOTALL)
    for m in pattern.finditer(css_text):
        props = _extract_props_from_block(m.group(1))
        bg_raw = (props.get('background-color') or
                  _extract_shorthand_bg(props.get('background', '')))
        if bg_raw:
            rgb = parse_color(bg_raw)
            if rgb is not None and rgb not in bgs:
                bgs.append(rgb)
    return bgs


def fix_css_text(css_text: str,
                 threshold_normal: float = 4.5,
                 threshold_large: float = 3.0) -> Tuple[str, List[str]]:
    """
    Scan a complete CSS text for color/background-color pairs that violate
    WCAG 2.1 contrast requirements. Fix violations in place.

    Context-aware: before changing a foreground color that appears to fail
    against the default white background, we check whether that color already
    achieves sufficient contrast against ANY background explicitly declared
    elsewhere in the same stylesheet.  If it does, the color is intentionally
    paired with a dark (or otherwise non-white) container — we leave it alone
    to avoid breaking a deliberately designed colour scheme.

    Returns:
        (fixed_css_text, list_of_fix_descriptions)
    """
    fixes: List[str] = []

    # Pre-scan: collect every background colour in the file.
    # Used below to detect intentional light-on-dark colour pairs.
    all_backgrounds = _collect_all_backgrounds(css_text)

    # Determine the most conservative light background to use as the effective
    # default when a rule declares `color` but no `background-color`.
    #
    # Stylesheets commonly set the page/body background in one rule and the
    # text color in another (e.g. body{background-color:#fdf2fa} + p{color:…}).
    # Using pure white (#fff) as the default underestimates contrast for
    # near-white backgrounds, because a color that barely passes 4.5:1 on
    # #ffffff may fall below 4.5:1 on a slightly less-bright background.
    #
    # Strategy: among all light backgrounds declared anywhere in the stylesheet
    # (luminance ≥ 0.7), pick the darkest one (lowest luminance) — that is the
    # worst-case surface the text could be rendered on.  If no light background
    # is found, fall back to pure white.
    light_bgs = [
        (relative_luminance(*bg), bg)
        for bg in all_backgrounds
        if relative_luminance(*bg) >= 0.7
    ]
    if light_bgs:
        _effective_default_bg = min(light_bgs, key=lambda x: x[0])[1]
    else:
        _effective_default_bg = _DEFAULT_BG

    # Regex to find CSS rules: selector { ... }
    # We process each rule body individually, rewriting color values.
    # We use a simple brace-matching approach (handles most real EPUBs).
    def _fix_rule(m: re.Match) -> str:
        selector = m.group(1)
        body = m.group(2)

        props = _extract_props_from_block(body)

        # Resolve foreground and background
        fg_raw = props.get('color')
        bg_raw = (props.get('background-color') or
                  _extract_shorthand_bg(props.get('background', '')))

        fg_rgb = parse_color(fg_raw) if fg_raw else None

        # If this rule explicitly declares its own background, use it.
        # Otherwise use the most conservative light background found in the
        # stylesheet (see _effective_default_bg above), so that text colours
        # are evaluated against the actual rendered surface rather than an
        # idealised pure white.
        has_explicit_bg = bg_raw is not None
        bg_rgb = parse_color(bg_raw) if has_explicit_bg else _effective_default_bg

        if fg_rgb is None or bg_rgb is None:
            return m.group(0)  # Cannot analyse — leave unchanged

        threshold = (threshold_large if is_large_text(props)
                     else threshold_normal)
        ratio = contrast_ratio(fg_rgb, bg_rgb)

        if ratio >= threshold:
            return m.group(0)  # Already compliant against its own background

        # The rule fails against its own background (or the assumed white
        # default).  Before rewriting, check whether the foreground colour
        # already achieves good contrast against ANY other background declared
        # in this stylesheet.  If it does, AND the foreground is a genuinely
        # light colour (luminance > 0.4), the colour is likely intentional
        # (e.g. near-white text designed for a dark parent div) — leave it
        # unchanged to avoid breaking a deliberately designed colour scheme.
        #
        # The luminance guard is essential: mid-range colours such as soft
        # pinks, light oranges or pastel purples (luminance ≤ 0.4) trivially
        # pass against any dark background in the stylesheet, which would cause
        # the heuristic to exempt them even when they are only ever used on
        # white/light pages where they genuinely fail.
        if not has_explicit_bg and relative_luminance(*fg_rgb) > 0.55:
            for other_bg in all_backgrounds:
                if contrast_ratio(fg_rgb, other_bg) >= threshold:
                    return m.group(0)  # Intentional pairing — do not touch

        # Fix the foreground color
        new_fg = fix_color_for_contrast(fg_rgb, bg_rgb, threshold)
        new_hex = _rgb_to_hex(*new_fg)
        old_hex = _rgb_to_hex(*fg_rgb)

        fixes.append({'key': 'xfix_contrast',
                       'args': {'selector': selector.strip(),
                                'old': old_hex,
                                'new': f'{new_hex} (ratio {ratio:.2f}\u2192\u2265{threshold:.1f})'}})

        # Replace only the `color` value in the block, preserving other props.
        # If the original declaration had !important we keep it, since it was
        # added by css_consolidator to maintain inline-style precedence.
        def _replace_color(cm: re.Match) -> str:
            original = cm.group(0)
            important = ' !important' if re.search(r'!important', original, re.IGNORECASE) else ''
            return f'color: {new_hex}{important}'

        new_body = re.sub(
            r'\bcolor\s*:\s*[^;}{]+',
            _replace_color,
            body,
            count=1,
        )
        return f'{selector}{{{new_body}}}'

    # Match CSS rules (selector { body }) — handles multi-line rules
    pattern = re.compile(
        r'([^{}/]+?)\{([^{}]*?)\}',
        re.DOTALL,
    )
    fixed_css = pattern.sub(_fix_rule, css_text)
    return fixed_css, fixes


def _extract_shorthand_bg(bg_val: str) -> Optional[str]:
    """
    Try to extract a color from a `background` shorthand value.
    Returns the color token if identifiable, else None.
    """
    if not bg_val:
        return None
    # The color in a background shorthand can be any token; look for
    # something that parses as a color.
    for token in bg_val.split():
        if parse_color(token) is not None:
            return token
    # Handle rgb()/rgba()/hsl() spanning multiple tokens separated by commas
    m = re.search(r'(rgba?\([^)]+\)|hsla?\([^)]+\)|#[0-9a-fA-F]+)', bg_val)
    if m:
        return m.group(1)
    return None


# Regex that matches a selector containing an <a> anchor element selector.
# Catches: bare `a`, `a:link`, `a:visited`, `a:hover`, `a:focus`, `a:active`,
# `.class a`, `p a`, `a.class`, `a[href]`, etc.
# Does NOT match selectors like `.label`, `.abstract`, etc.
_LINK_SELECTOR_RE = re.compile(r'(?:^|[\s,>+~(])a(?:$|[\s:.,#\[\(>+~{])', re.IGNORECASE)


def fix_link_underline(css_text: str) -> Tuple[str, List[dict]]:
    """
    Ensure links are visually distinguishable from surrounding text without
    relying on colour alone (WCAG 1.4.1 / ACE link-in-text-block).

    Two-phase strategy:

    Phase 1 — direct fix:
      Find rules whose selector explicitly targets <a> elements and replace
      any 'text-decoration: none' with 'text-decoration: underline'.
      Handles patterns like  a { … }  /  a:hover { … }  /  .nav a { … }.

    Phase 2 — safety-net override:
      After phase 1, if any 'text-decoration: none' still remains in the
      stylesheet (e.g. a utility class like '.nounder' that is applied to
      <a> elements in the HTML), append a final rule:
        a { text-decoration: underline !important; }
      Placing it last ensures maximum cascade priority without touching the
      rest of the stylesheet.  The rule is only added when actually needed —
      not injected into every EPUB.

    Returns (fixed_css, list_of_fix_dicts).
    """
    fixes: List[dict] = []
    pattern = re.compile(r'([^{}/]+?)\{([^{}]*?)\}', re.DOTALL)

    # ── Phase 1: fix direct <a> selector rules ────────────────────────────
    def _fix_rule(m: re.Match) -> str:
        selector = m.group(1)
        body     = m.group(2)

        # Only rules whose selector targets <a> elements
        if not _LINK_SELECTOR_RE.search(selector):
            return m.group(0)

        # Only if text-decoration: none is present
        if not re.search(r'\btext-decoration\s*:\s*none\b', body, re.IGNORECASE):
            return m.group(0)

        new_body = re.sub(
            r'\btext-decoration\s*:\s*none\b',
            'text-decoration: underline',
            body,
            flags=re.IGNORECASE,
        )
        fixes.append({'key': 'xfix_link_underline',
                      'args': {'selector': selector.strip()}})
        return f'{selector}{{{new_body}}}'

    fixed = pattern.sub(_fix_rule, css_text)

    # ── Phase 2: safety-net override for class/id rules ───────────────────
    # If 'text-decoration: none' still appears anywhere (e.g. in a utility
    # class like '.nounder' that happens to be applied to <a> elements),
    # append a high-priority rule that guarantees links are underlined.
    _SAFETY_RULE = '\n/* AccesPub a11y fix: ensure links are always underlined */\na { text-decoration: underline !important; }\n'
    _td_none_re  = re.compile(r'\btext-decoration\s*:\s*none\b', re.IGNORECASE)
    if _td_none_re.search(fixed) and _SAFETY_RULE.strip() not in fixed:
        fixed += _SAFETY_RULE
        fixes.append({'key': 'xfix_link_underline_override', 'args': {}})

    return fixed, fixes


def fix_css_file(path: str,
                 threshold_normal: float = 4.5,
                 threshold_large: float = 3.0) -> List[str]:
    """
    Read a CSS file, fix all contrast violations and link-underline issues,
    write it back.  Returns a list of fix descriptions (empty if no fixes).
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            original = fh.read()
    except OSError as e:
        return [f'[Error] Could not read {path}: {e}']

    all_fixes: List[dict] = []

    fixed, contrast_fixes = fix_css_text(original, threshold_normal, threshold_large)
    all_fixes.extend(contrast_fixes)

    fixed, underline_fixes = fix_link_underline(fixed)
    all_fixes.extend(underline_fixes)

    if all_fixes:
        try:
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(fixed)
        except OSError as e:
            return [f'[Error] Could not write {path}: {e}']

    return all_fixes


# ---------------------------------------------------------------------------
# Analyse CSS for contrast issues (without fixing — for reporting)
# ---------------------------------------------------------------------------

def analyse_css_text(css_text: str,
                     threshold_normal: float = 4.5,
                     threshold_large: float = 3.0) -> List[Dict]:
    """
    Scan CSS text for contrast violations and return a list of dicts:
      { 'selector', 'fg', 'bg', 'ratio', 'threshold', 'large_text' }
    Does NOT modify the CSS.
    """
    issues: List[Dict] = []
    pattern = re.compile(r'([^{}/]+?)\{([^{}]*?)\}', re.DOTALL)

    for m in pattern.finditer(css_text):
        selector = m.group(1).strip()
        body = m.group(2)
        props = _extract_props_from_block(body)

        fg_raw = props.get('color')
        bg_raw = (props.get('background-color') or
                  _extract_shorthand_bg(props.get('background', '')))

        fg_rgb = parse_color(fg_raw) if fg_raw else None
        bg_rgb = parse_color(bg_raw) if bg_raw else _DEFAULT_BG

        if fg_rgb is None or bg_rgb is None:
            continue

        large = is_large_text(props)
        threshold = threshold_large if large else threshold_normal
        ratio = contrast_ratio(fg_rgb, bg_rgb)

        if ratio < threshold:
            issues.append({
                'selector': selector,
                'fg': _rgb_to_hex(*fg_rgb),
                'bg': _rgb_to_hex(*bg_rgb),
                'ratio': round(ratio, 2),
                'threshold': threshold,
                'large_text': large,
            })

    return issues


def analyse_css_file(path: str,
                     threshold_normal: float = 4.5,
                     threshold_large: float = 3.0) -> List[Dict]:
    """
    Read a CSS file and return a list of contrast violation dicts.
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            text = fh.read()
    except OSError:
        return []
    return analyse_css_text(text, threshold_normal, threshold_large)
