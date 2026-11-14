"""LocalAuditService: the MVP implementation of ``AuditService`` (single process, SQLite, asyncio queue)."""

from __future__ import annotations

import asyncio
import logging
import zlib
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from seoa.application.audit.orchestrator import AuditRunner
from seoa.application.audit.protocol import AuditEvent, AuditSummary, QAAnswerRecord
from seoa.application.ports import FetcherLike
from seoa.config import Settings
from seoa.domain import AuditMode, AuditRecord, AuditStatus

if TYPE_CHECKING:
    from seoa.infrastructure.persistence.repo import Repo

log = logging.getLogger("seoa.application.audit")
MAX_QA_PER_AUDIT = 20
_TERMINAL = {"completed", "partial", "failed", "canceled"}


class LocalAuditService:
    """Runs audits in this process: a worker pool over an asyncio queue.

    Every collaborator is injected (see ``seoa.bootstrap.build_local_service``): the store, the
    fetcher, the collaborators module ``ops`` that the pipeline calls out through, and the
    optional renderer / LLM provider / Search Console client.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        repo: Repo,
        fetcher: FetcherLike,
        ops: Any,
        renderer: Any = None,
        renderer_factory: Callable[[], Awaitable[Any]] | None = None,
        llm_provider: Any = None,
        workers: int = 2,
        gsc_client: Any = None,
    ) -> None:
        self._gsc_client = gsc_client
        self.settings = settings
        self.repo = repo
        self.ops = ops
        self._fetcher = fetcher
        self._renderer = renderer
        self._renderer_factory = renderer_factory
        self._own_renderer = False
        self._llm = llm_provider
        self._n_workers = workers
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._tasks: list[asyncio.Task[None]] = []
        self._waiters: dict[str, asyncio.Event] = {}
        self._runner: AuditRunner | None = None
        self._started = False

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        if self._started:
            return
        await self.repo.open()
        if self._renderer is None and self._renderer_factory and self.settings.render_enabled:
            try:
                self._renderer, self._own_renderer = await self._renderer_factory(), True
            except Exception as exc:  # no browser: render stage is skipped, audits still work
                log.warning("renderer unavailable: %s", type(exc).__name__)
                self._renderer = None
        self._runner = AuditRunner(
            self.repo,
            self.settings,
            self._fetcher,
            renderer=self._renderer,
            llm=self._llm,
            notify=self._notify,
            gsc_client=self._gsc_client,
            ops=self.ops,
        )
        # crash recovery: an audit that was running when the process died cannot be resumed in the MVP
        for aid in await self.repo.list_by_status("running"):
            await self.repo.update_audit(
                aid,
                status=AuditStatus.FAILED,
                error="interrupted",
                finished_at=datetime.now(UTC).isoformat(),
            )
        for aid in await self.repo.list_by_status("queued"):
            self._queue.put_nowait(aid)
        self._tasks = [asyncio.create_task(self._worker(i)) for i in range(self._n_workers)]
        self._started = True

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        if self._fetcher:
            await self._fetcher.close()
        if self._renderer is not None and self._own_renderer:
            await self._renderer.close()
        await self.repo.close()
        self._started = False

    async def _worker(self, n: int) -> None:
        assert self._runner is not None
        while True:
            aid = await self._queue.get()
            try:
                await self._runner.run(aid)
            except asyncio.CancelledError:
                raise
            except Exception:  # the runner handles its own errors; this is the last resort
                log.exception("worker %d: audit %s crashed", n, aid)
            finally:
                self._queue.task_done()
                self._notify(aid)

    def _notify(self, aid: str) -> None:
        ev = self._waiters.get(aid)
        if ev:
            ev.set()

    # ------------------------------------------------------------------ API

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
        parent: str | None = None,
    ) -> str:
        url = (url or "").strip()
        if not url or len(url) > 2048:
            raise ValueError("invalid url")
        opts = {
            "max_pages": max_pages,
            "enable_llm": enable_llm,
            "lang": lang if lang in ("tr", "en") else "tr",
            "extra_urls": (extra_urls or [])[:20],
            "keywords": [k.strip()[:80] for k in (keywords or []) if k.strip()][:20],
            "competitors": [c.strip()[:300] for c in (competitors or []) if c.strip()][:5],
        }
        seed = zlib.crc32(f"{url}|{datetime.now(UTC).isoformat()}".encode())
        budget = {
            "max_pages": min(
                max_pages or self.settings.max_pages_default, self.settings.max_pages_cap
            ),
            "llm_pages": self.settings.llm_max_pages,
            "llm_scope_cap_usd": 0.75,
        }
        aid = await self.repo.create_audit(
            url=url, mode=mode, options=opts, seed=seed, parent=parent, budget=budget
        )
        await self.repo.add_event(
            aid, {"status": AuditStatus.QUEUED, "message_key": "audit.queued"}
        )
        self._queue.put_nowait(aid)
        return aid

    def file_path(self, audit_id: str, name: str) -> Path | None:
        return self.repo.file_path(audit_id, name)

    async def get_audit(self, audit_id: str) -> AuditRecord | None:
        return await self.repo.load_record(audit_id)

    async def list_audits(self, limit: int = 20) -> list[AuditSummary]:
        return await self.repo.list_summaries(limit)

    async def suggest_keywords(self, url: str) -> dict[str, Any]:
        """Top Search Console queries of the site (last 28 days), most shown first.

        ``status`` is ``ok``, ``empty`` or the Search Console state (not-connected, ...); the
        keywords are the site's own search queries, never invented.
        """
        from seoa.application.analysis.search_console.property import resolve_property
        from seoa.application.ports import GscError

        client = self._gsc_client
        if client is None:
            return {"status": "not-configured", "keywords": []}
        state = client.oauth.status(client.user_id)
        if not state["configured"]:
            return {"status": "not-configured", "keywords": []}
        if not state["connected"]:
            return {"status": "not-connected", "keywords": []}
        try:
            res = resolve_property(url, await client.list_properties())
            if res.property is None:
                reason = "no-permission" if res.reason == "no-permission" else "property-not-found"
                return {"status": reason, "keywords": []}
            rows = await client.search_analytics(
                res.property, days=28, dimensions=["query"], row_limit=12
            )
        except GscError as exc:
            return {
                "status": "not-connected" if exc.code == "not-connected" else "error",
                "keywords": [],
            }
        found = [
            {
                "query": str(r["keys"][0]).strip(" \"'")[:80],
                "impressions": int(r.get("impressions", 0)),
                "clicks": int(r.get("clicks", 0)),
            }
            for r in rows
            if r.get("keys")
        ]
        return {"status": "ok" if found else "empty", "keywords": found}

    async def test_llm(self) -> str:
        """One tiny real call with the saved key (see ``ops.llm_ping``)."""
        return str(await self.ops.llm_ping(self._llm))

    async def list_qa(self, audit_id: str) -> list[dict[str, Any]]:
        return await self.repo.list_qa(audit_id)

    async def get_profile(self, url_or_host: str) -> dict[str, list[str]]:
        return await self.repo.get_profile(url_or_host)

    async def save_profile(
        self, url_or_host: str, keywords: list[str], competitors: list[str]
    ) -> None:
        await self.repo.save_profile(url_or_host, keywords, competitors)

    async def list_site_audits(self, host: str, limit: int = 20) -> list[AuditSummary]:
        return await self.repo.list_site_audits(host, limit)

    async def events(self, audit_id: str, after: int = 0) -> AsyncIterator[AuditEvent]:
        ev = self._waiters.setdefault(audit_id, asyncio.Event())
        seq = after
        while True:
            ev.clear()
            batch = await self.repo.events_after(audit_id, seq)
            for e in batch:
                seq = e.seq
                yield e
            status = await self.repo.get_status(audit_id)
            if status is None or (status in _TERMINAL and not batch):
                return
            try:
                await asyncio.wait_for(ev.wait(), timeout=1.0)
            except TimeoutError:
                pass

    async def cancel(self, audit_id: str) -> bool:
        return await self.repo.request_cancel(audit_id)

    async def rerun(self, audit_id: str, modules: list[str]) -> str:
        """MVP: a rerun is a fresh audit linked to its parent (an LLM-only rerun from the stored
        snapshot is deferred, see docs/architecture/09 s.16.1)."""
        opts = await self.repo.get_option(audit_id)
        if not opts:
            raise KeyError(audit_id)
        want_llm = "llm" in modules or "all" in modules
        return await self.create_audit(
            opts["_url"],
            AuditMode(opts["_mode"]),
            max_pages=opts.get("max_pages"),
            enable_llm=bool(opts.get("enable_llm", True)) if want_llm or not modules else False,
            lang=opts.get("lang", "tr"),
            extra_urls=opts.get("extra_urls"),
            keywords=opts.get("keywords"),
            competitors=opts.get("competitors"),
            parent=audit_id,
        )

    async def ask(self, audit_id: str, question: str) -> QAAnswerRecord:
        from seoa.application.reporting.builder import build_report

        rec = await self.repo.load_record(audit_id)
        if rec is None:
            raise KeyError(audit_id)
        lang = (await self.repo.get_option(audit_id)).get("lang", "tr")
        if self._llm is None:
            return QAAnswerRecord(answer="LLM is not configured.", out_of_scope=True)
        if await self.repo.count_qa(audit_id) >= MAX_QA_PER_AUDIT:
            return QAAnswerRecord(
                answer="Question limit for this audit reached.", out_of_scope=True
            )
        report = build_report(rec, lang).model_dump(mode="json")
        ans: QAAnswerRecord = await self.ops.answer_question(
            self._llm, audit_id, report, question, lang
        )
        await self.repo.add_qa(audit_id, question, ans.model_dump(mode="json"))
        return ans

    async def spend(self) -> dict[str, float]:
        if self._llm is None:
            return {"spent_usd": 0.0, "cap_usd": self.settings.llm_budget_usd}
        snap = self._llm.snapshot()
        return {
            "spent_usd": float(snap.get("spent_usd", 0.0)),
            "cap_usd": float(snap.get("cap_usd", self.settings.llm_budget_usd)),
        }
