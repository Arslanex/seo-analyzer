"""Domain authority module (belge 12 B2): OpenPageRank estimate for the site's registrable domain.

Needs ``SEOA_OPENPAGERANK_KEY``; without it the result is ``NotChecked("authority",
"no-api-key")``. A third-party estimate, not a Google metric: it produces no findings and never
touches a score.
"""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import BaseModel

from seoa.application.analysis.plugin import AnalysisInputs, ModuleResult, register_module
from seoa.domain import NotChecked


class AuthoritySignal(BaseModel):
    domain: str = ""
    page_rank_decimal: float | None = None  # 0..10, one decimal place
    page_rank_integer: int | None = None
    rank: int | None = None  # global rank; larger numbers are less authoritative
    error: str | None = None


class AuthorityModule:
    name = "authority"
    kind = "authority"
    timeout_s = 20.0

    async def run(self, inp: AnalysisInputs) -> ModuleResult:
        key = getattr(inp.settings, "openpagerank_key", None)
        if not key:
            return ModuleResult(
                kind=self.kind,
                not_checked=[NotChecked(check_id=self.kind, reason_code="no-api-key")],
            )
        host = urlparse(inp.origin).hostname or ""
        data: AuthoritySignal = await inp.ops.fetch_authority(host, key)
        if data.error:
            return ModuleResult(
                kind=self.kind,
                not_checked=[NotChecked(check_id=self.kind, reason_code=f"authority-{data.error}")],
            )
        return ModuleResult(kind=self.kind, data=data)


register_module(AuthorityModule())

__all__ = ["AuthorityModule"]
