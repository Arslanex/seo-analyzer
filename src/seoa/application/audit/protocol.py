"""Service contract between the API/UI and the pipeline (implemented by service.audit_service)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from seoa.domain import AuditMode, AuditRecord, AuditStatus, Stage, StageStatus


class AuditEvent(BaseModel):
    seq: int
    audit_id: str
    stage: Stage | None = None
    status: StageStatus | AuditStatus | None = None
    message_key: str = ""
    message: str = ""
    pages_fetched: int | None = None
    pages_planned: int | None = None
    ts: datetime


class AuditSummary(BaseModel):
    id: str
    target_url: str
    mode: AuditMode
    status: AuditStatus
    overall: float | None = None
    coverage_pct: float | None = None
    created_at: datetime


class QAAnswerRecord(BaseModel):
    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    out_of_scope: bool = False
    cost_usd: float = 0.0


class AuditService(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def create_audit(
        self,
        url: str,
        mode: AuditMode,
        *,
        max_pages: int | None = None,
        enable_llm: bool = True,
        lang: str = "tr",
        extra_urls: list[str] | None = None,
        keywords: list[str] | None = None,
        competitors: list[str] | None = None,
    ) -> str: ...
    async def get_audit(self, audit_id: str) -> AuditRecord | None: ...
    async def list_audits(self, limit: int = 20) -> list[AuditSummary]: ...
    async def list_site_audits(self, host: str, limit: int = 20) -> list[AuditSummary]: ...
    async def list_qa(self, audit_id: str) -> list[dict[str, Any]]: ...
    async def test_llm(self) -> str: ...
    async def suggest_keywords(self, url: str) -> dict[str, Any]: ...
    async def get_profile(self, url_or_host: str) -> dict[str, list[str]]: ...
    async def save_profile(
        self, url_or_host: str, keywords: list[str], competitors: list[str]
    ) -> None: ...
    def events(self, audit_id: str, after: int = 0) -> AsyncIterator[AuditEvent]: ...
    async def cancel(self, audit_id: str) -> bool: ...
    async def rerun(self, audit_id: str, modules: list[str]) -> str: ...
    async def ask(self, audit_id: str, question: str) -> QAAnswerRecord: ...
    def file_path(self, audit_id: str, name: str) -> Path | None: ...
    async def spend(self) -> dict[str, float]: ...  # {"spent_usd":..., "cap_usd":...}
