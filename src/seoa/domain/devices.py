"""Viewports and user agent used to render a page as a desktop or a phone."""

from __future__ import annotations

DESKTOP_VIEWPORT = {"width": 1366, "height": 768}
MOBILE_VIEWPORT = {"width": 390, "height": 844}
MOBILE_DPR = 3.0
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
)
