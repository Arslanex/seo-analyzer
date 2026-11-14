"""Analysis modules (belge 12 s.4): a module takes ``AnalysisInputs`` and returns a ``ModuleResult``.

The orchestrator runs every registered module concurrently with a timeout; a module that fails
or times out is logged and skipped - it never breaks the audit. A module's JSON block is stored
under its ``kind`` and the report reads it from ``AuditRecord.extras[kind]``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

from seoa.application.analysis.types import AnalysisPage
from seoa.application.ports import FetcherLike
from seoa.config import Settings
from seoa.domain import AuditMode, FetchResult, Finding, NotChecked


@dataclass
class AnalysisInputs:
    audit_id: str
    mode: AuditMode
    entry_url: str
    origin: str
    entry_fetch: FetchResult
    entry_html: str  # rendered HTML when the page was rendered, else the raw HTML
    entry_parsed: Any  # ParsedPage | None
    pages: list[AnalysisPage]
    fetcher: FetcherLike
    renderer: Any  # Renderer | None
    settings: Settings
    lang: str | None  # detected page language
    output_lang: str  # report language (tr | en)
    options: dict[str, Any]  # user inputs: keywords, competitors, ...
    robots: Any  # RobotsView
    save_file: Callable[
        [str, bytes], Awaitable[str]
    ]  # store a binary artefact (screenshot); returns its name
    sitemap_urls: set[str] = field(default_factory=set)
    ops: Any = (
        None  # the collaborators module: modules call out through it, never to infrastructure
    )


@dataclass
class ModuleResult:
    kind: str
    data: BaseModel | list[BaseModel] | None = None
    findings: list[Finding] = field(default_factory=list)
    not_checked: list[NotChecked] = field(default_factory=list)
    available: set[str] = field(
        default_factory=set
    )  # scoring requirements this module provides (e.g. "gsc")


class AnalysisModule(Protocol):
    name: str
    kind: str  # key under AuditRecord.extras
    timeout_s: float

    async def run(self, inp: AnalysisInputs) -> ModuleResult: ...


_MODULES: dict[str, AnalysisModule] = {}


def register_module(module: AnalysisModule) -> AnalysisModule:
    _MODULES[module.name] = module
    return module


# Module files by name: each registers its rules, messages and itself on import.
MODULES_PACKAGE = "seoa.application.analysis.modules"
MODULE_FILES = (
    "techstack",
    "site_setup",
    "previews",
    "screenshots",
    "readability",
    "hreflang",
    "schema_suggest",
    "agentic",
    "competitors",
    "local",
    "sitemap_gen",
    "authority",
)


def load_module_files() -> None:
    """Import the module files that exist (idempotent); a missing file is skipped, a broken one raises."""
    import importlib

    for name in MODULE_FILES:
        full = f"{MODULES_PACKAGE}.{name}"
        try:
            importlib.import_module(full)
        except ModuleNotFoundError as exc:
            if exc.name != full:
                raise


def modules() -> list[AnalysisModule]:
    load_module_files()
    return [m for _, m in sorted(_MODULES.items())]
