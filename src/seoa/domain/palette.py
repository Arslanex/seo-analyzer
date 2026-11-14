"""Severity and score-band colours: one source for the HTML pages and the contrast checks."""

from __future__ import annotations

from typing import Any

from seoa.domain import Severity

# severity -> shape, (light fg, light bg), (dark fg, dark bg). Contrast ratios in belge 06 s.9.2.
SEVERITY_STYLES: dict[Severity, dict[str, Any]] = {
    Severity.CRITICAL: {
        "shape": "octagon",
        "light": ("#b42318", "#fdeceb"),
        "dark": ("#ff8b83", "#3b1614"),
    },
    Severity.HIGH: {
        "shape": "triangle",
        "light": ("#a8480a", "#fdf0e3"),
        "dark": ("#ffa766", "#3a2210"),
    },
    Severity.MEDIUM: {
        "shape": "diamond",
        "light": ("#7a5b00", "#fbf3d4"),
        "dark": ("#f0cf5b", "#352b0a"),
    },
    Severity.LOW: {
        "shape": "circle",
        "light": ("#1d5bbf", "#e8f0fc"),
        "dark": ("#8ab4ff", "#14264a"),
    },
    Severity.INFO: {
        "shape": "ring",
        "light": ("#475467", "#eef0f3"),
        "dark": ("#b4bcc9", "#242b38"),
    },
}
BAND_STYLES = {"good": "#1b6b43", "attention": "#8f5300", "poor": "#b42318"}
