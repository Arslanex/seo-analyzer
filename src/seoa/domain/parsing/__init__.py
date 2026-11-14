"""HTML parsing into the serialisable ``ParsedPage``."""

from seoa.domain.parsing.html import (
    ImageInfo,
    JsonLdBlock,
    LinkInfo,
    ParsedPage,
    canonicalize_url,
    parse_html,
    trim,
    url_match_key,
    words_measurable,
)

__all__ = [
    "ImageInfo",
    "JsonLdBlock",
    "LinkInfo",
    "ParsedPage",
    "canonicalize_url",
    "parse_html",
    "trim",
    "url_match_key",
    "words_measurable",
]
