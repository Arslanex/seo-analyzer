"""SPA / hydration-shell detection.

Faithful port of the upstream project ``scripts/render_page.py::_is_spa`` (MIT, see NOTICE).
The heuristic is deliberately conservative: an unnecessary render is expensive, so
SSR/SSG pages that keep their framework root markers but ship real text are NOT
flagged.
"""

from __future__ import annotations

import re

# A marker only counts while meaningful body text is sparse (< BUILDER_SPARSE_TEXT_MAX).
SPA_SHELL_PATTERNS: tuple[str, ...] = (
    '<div id="root"></div>',
    '<div id="__next">',
    '<div id="app"></div>',
    '<div id="__nuxt">',
    "data-svelte-h=",
    "<astro-island ",
    "you need to enable javascript",
    "please enable javascript",
)

# Builder markers are supporting evidence only: Wix, Webflow and Squarespace can all
# serve complete HTML, so two markers of the SAME builder plus sparse text are required.
BUILDER_FINGERPRINT_GROUPS: tuple[tuple[str, ...], ...] = (
    ("wix-warmup-data", "static.parastorage.com", 'content="wix.com'),
    ("data-wf-page", "data-wf-site"),
    ('content="squarespace', "static1.squarespace.com"),
)

BUILDER_SPARSE_TEXT_MAX = 400
THIN_BODY_TEXT_MAX = 100  # example.com has ~125 chars of body text and must not trip this

_TAG_STRIP = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
_NON_VISIBLE_STRIP = re.compile(
    r"<(script|style|template|noscript)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)


def visible_body_text(lower_html: str) -> str:
    """Whitespace-collapsed text of ``<body>`` without script/style/template/noscript.

    ``lower_html`` must already be lower-cased (as the source does); returns ``""``
    when there is no well-formed ``<body>...</body>``.
    """
    start = lower_html.find("<body")
    end = lower_html.rfind("</body>")
    if start == -1 or end <= start:
        return ""
    body = _NON_VISIBLE_STRIP.sub(" ", lower_html[start:end])
    return _WHITESPACE.sub(" ", _TAG_STRIP.sub(" ", body)).strip()


def is_spa(raw_html: str | None) -> bool:
    """True when ``raw_html`` looks like a sparse client-side hydration shell."""
    if not raw_html:
        return True
    lc = raw_html.lower()
    text = visible_body_text(lc)
    if len(text) < BUILDER_SPARSE_TEXT_MAX and any(p in lc for p in SPA_SHELL_PATTERNS):
        return True
    if len(text) < BUILDER_SPARSE_TEXT_MAX:
        for markers in BUILDER_FINGERPRINT_GROUPS:
            if sum(marker in lc for marker in markers) >= 2:
                return True
    # Very thin <body> suggests JS-rendered content even without a known shell.
    start = lc.find("<body")
    end = lc.rfind("</body>")
    return start != -1 and end > start and len(text) < THIN_BODY_TEXT_MAX
