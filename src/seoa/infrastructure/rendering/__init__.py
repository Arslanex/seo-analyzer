"""Rendering: SPA detection, raw-vs-rendered gap, guarded headless browser."""

from seoa.infrastructure.rendering.browser import Renderer, RenderResult
from seoa.infrastructure.rendering.js_gap import JsGap, js_gap, js_gap_reasons
from seoa.infrastructure.rendering.spa import is_spa, visible_body_text

__all__ = [
    "JsGap",
    "RenderResult",
    "Renderer",
    "is_spa",
    "js_gap",
    "js_gap_reasons",
    "visible_body_text",
]
