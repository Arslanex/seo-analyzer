"""Composition root: the one place that knows every concrete implementation.

Layers below receive their collaborators through constructors; this module builds them from the
environment (``Settings``) and wires them together. Entry points (``scripts/``) call it.
"""

from __future__ import annotations

from typing import Any

from seoa.application.audit.service import LocalAuditService
from seoa.application.ports import FetcherLike
from seoa.config import Settings, get_settings
from seoa.infrastructure import adapters
from seoa.infrastructure.http.fetcher import Fetcher
from seoa.infrastructure.persistence.repo import Repo


async def _start_renderer() -> Any:
    from seoa.infrastructure.rendering import Renderer

    renderer = Renderer()
    await renderer.start()
    return renderer


def build_local_service(
    settings: Settings | None = None,
    *,
    fetcher: FetcherLike | None = None,
    renderer: Any = None,
    llm_provider: Any = None,
    workers: int = 2,
    gsc_client: Any = None,
) -> LocalAuditService:
    """The single-process audit service: SQLite store, asyncio queue, real network and browser.

    Pass ``fetcher`` / ``renderer`` / ``llm_provider`` to replace a collaborator (tests do).
    """
    cfg = settings or get_settings()
    if llm_provider is None and cfg.anthropic_api_key:
        llm_provider = adapters.LLMProvider(cfg)
    return LocalAuditService(
        cfg,
        repo=Repo(cfg.db_path, cfg.data_dir / "objects"),
        fetcher=fetcher or Fetcher(cfg),
        ops=adapters,
        renderer=renderer,
        renderer_factory=_start_renderer,
        llm_provider=llm_provider,
        workers=workers,
        gsc_client=gsc_client,
    )
