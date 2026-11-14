"""Input type shared by the deep-analysis modules (the pipeline builds it from fetched pages)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from seoa.domain.parsing.html import ParsedPage


@dataclass
class AnalysisPage:
    """One fetched (and parsed) page of the sample."""

    url: str
    final_url: str | None
    status: int | None
    headers: dict[str, str] = field(default_factory=dict)  # lower-cased names
    parsed: ParsedPage | None = None
    sample_kind: Literal["core", "exploration"] = "core"
    error: str | None = None  # stable fetch error code, None when the fetch worked

    @property
    def effective_url(self) -> str:
        return self.final_url or self.url
