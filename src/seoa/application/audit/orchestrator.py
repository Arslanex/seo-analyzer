"""Audit orchestration: a deterministic state machine over the stages (belge 02).

No LLM decides anything here. Stage results are persisted as they are produced,
so a crash leaves a usable partial record; cancellation is cooperative.
"""

from __future__ import annotations

import asyncio
import logging
import time
import zlib
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from seoa.application.audit import rules as _rules  # noqa: F401  (registers pipeline rules)
from seoa.application.crawl.detect import detect_business_type, detect_lang
from seoa.application.crawl.sampling import Candidate, select_sample
from seoa.application.ports import FetcherLike
from seoa.application.rules_loader import load_all_rules
from seoa.config import Settings
from seoa.domain import (
    SEVERITY_ORDER,
    AuditMode,
    AuditStatus,
    Category,
    Finding,
    NotChecked,
    PageRecord,
    Severity,
    Stage,
    StageStatus,
)
from seoa.domain.ids import new_id
from seoa.domain.rules import registry
from seoa.domain.scoring import GateInputs, compute_scores, page_score
from seoa.domain.url_safety import URLSafetyError, check_url
from seoa.domain.urls import in_scope, is_crawlable_page, normalize_url

if TYPE_CHECKING:
    from seoa.infrastructure.persistence.repo import Repo

log = logging.getLogger("seoa.application.audit")

Notify = Callable[[str], None]


class _Cancelled(Exception):
    pass


class _Fatal(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


def _html_ok(fr: Any) -> bool:
    return fr.error is None and fr.status is not None and fr.html is not None


class AuditRunner:
    def __init__(
        self,
        repo: Repo,
        settings: Settings,
        fetcher: FetcherLike,
        *,
        renderer: Any = None,
        llm: Any = None,
        notify: Notify | None = None,
        gsc_client: Any = None,
        ops: Any = None,
    ) -> None:
        # ``ops`` is the collaborators module (``seoa.infrastructure.adapters``): parsing, checks,
        # rendering, LLM and the optional data providers. It is injected so this layer never
        # imports infrastructure; tests monkeypatch its functions.
        self.ops = ops
        load_all_rules()  # scoring and reports need the full rule catalogue
        self.gsc_client = gsc_client
        self.repo = repo
        self.s = settings
        self.fetcher = fetcher
        self.renderer = renderer
        self.llm = llm
        self._notify = notify or (lambda aid: None)

    # ------------------------------------------------------------------ plumbing

    async def _emit(self, aid: str, **ev: Any) -> None:
        await self.repo.add_event(aid, ev)
        self._notify(aid)

    async def _check_cancel(self, aid: str) -> None:
        if await self.repo.is_cancel_requested(aid):
            raise _Cancelled

    async def _stage(
        self, aid: str, stage: Stage, fn: Callable[[], Awaitable[Any]], *, skip: bool = False
    ) -> Any:
        await self._check_cancel(aid)
        if skip:
            await self.repo.set_stage(aid, stage, StageStatus.SKIPPED)
            await self._emit(
                aid,
                stage=stage,
                status=StageStatus.SKIPPED,
                message_key=f"stage.{stage.value}.skipped",
            )
            return None
        await self.repo.set_stage(aid, stage, StageStatus.RUNNING)
        await self._emit(
            aid, stage=stage, status=StageStatus.RUNNING, message_key=f"stage.{stage.value}.start"
        )
        try:
            out = await fn()
        except (_Cancelled, _Fatal):
            await self.repo.set_stage(aid, stage, StageStatus.FAILED)
            raise
        except Exception as exc:
            log.exception("stage %s failed", stage.value)
            await self.repo.set_stage(aid, stage, StageStatus.FAILED, f"{type(exc).__name__}")
            await self._emit(
                aid,
                stage=stage,
                status=StageStatus.FAILED,
                message_key=f"stage.{stage.value}.failed",
            )
            raise
        await self.repo.set_stage(aid, stage, StageStatus.DONE)
        await self._emit(
            aid, stage=stage, status=StageStatus.DONE, message_key=f"stage.{stage.value}.done"
        )
        return out

    # ------------------------------------------------------------------ run

    async def run(self, aid: str) -> None:
        t0 = time.monotonic()
        opts = await self.repo.get_option(aid)
        mode = AuditMode(opts["_mode"])
        await self.repo.update_audit(aid, status=AuditStatus.RUNNING)
        await self._emit(aid, status=AuditStatus.RUNNING, message_key="audit.running")
        ctx: dict[str, Any] = {
            "opts": opts,
            "mode": mode,
            "findings": [],
            "not_checked": [],
            "partial_reasons": [],
        }
        try:
            await self._pipeline(aid, ctx)
            status = AuditStatus.PARTIAL if ctx["partial_reasons"] else AuditStatus.COMPLETED
            await self.repo.update_audit(
                aid,
                status=status,
                finished_at=datetime.now(UTC).isoformat(),
                cost={**ctx.get("cost", {}), "wall_ms": int((time.monotonic() - t0) * 1000)},
            )
            await self._emit(aid, status=status, message_key=f"audit.{status.value}")
        except _Cancelled:
            await self.repo.update_audit(
                aid, status=AuditStatus.CANCELED, finished_at=datetime.now(UTC).isoformat()
            )
            await self._emit(aid, status=AuditStatus.CANCELED, message_key="audit.canceled")
        except _Fatal as f:
            await self.repo.update_audit(
                aid,
                status=AuditStatus.FAILED,
                error=f"{f.code}: {f.detail}"[:300],
                finished_at=datetime.now(UTC).isoformat(),
            )
            await self._emit(aid, status=AuditStatus.FAILED, message_key=f"audit.failed.{f.code}")
        except Exception as exc:  # a bug, not a user error: keep what exists, say so
            log.exception("audit %s crashed", aid)
            await self.repo.update_audit(
                aid,
                status=AuditStatus.FAILED,
                error=f"internal-error: {type(exc).__name__}",
                finished_at=datetime.now(UTC).isoformat(),
            )
            await self._emit(
                aid, status=AuditStatus.FAILED, message_key="audit.failed.internal-error"
            )

    async def _pipeline(self, aid: str, ctx: dict[str, Any]) -> None:
        mode: AuditMode = ctx["mode"]
        await self._stage(aid, Stage.VALIDATE, lambda: self._validate(aid, ctx))
        await self._stage(aid, Stage.FETCH_ENTRY, lambda: self._fetch_entry(aid, ctx))
        await self._stage(aid, Stage.ROBOTS, lambda: self._robots(aid, ctx))
        await self._stage(
            aid, Stage.DISCOVERY, lambda: self._discovery(aid, ctx), skip=mode == AuditMode.PAGE
        )
        await self._stage(
            aid, Stage.SAMPLE, lambda: self._sample(aid, ctx), skip=mode == AuditMode.PAGE
        )
        await self._stage(
            aid, Stage.FETCH_PAGES, lambda: self._fetch_pages(aid, ctx), skip=mode == AuditMode.PAGE
        )
        await self._stage(
            aid,
            Stage.RENDER,
            lambda: self._render(aid, ctx),
            skip=not (self.s.render_enabled and self.renderer),
        )
        await self._stage(aid, Stage.MEASURE, lambda: self._measure(aid, ctx))
        await self._stage(aid, Stage.ANALYZE, lambda: self._analyze(aid, ctx))
        await self._stage(aid, Stage.SCORE, lambda: self._score(aid, ctx))
        llm_on = bool(ctx["opts"].get("enable_llm", True)) and self.llm is not None
        await self._stage(aid, Stage.ADVISE, lambda: self._advise(aid, ctx), skip=not llm_on)
        await self._stage(
            aid, Stage.SYNTHESIZE, lambda: self._synthesize(aid, ctx), skip=not llm_on
        )
        await self._stage(aid, Stage.REPORT, lambda: self._report(aid, ctx))

    # ------------------------------------------------------------------ stages

    async def _validate(self, aid: str, ctx: dict[str, Any]) -> None:
        raw = ctx["opts"]["_url"].strip()
        if "://" not in raw:
            raw = "https://" + raw
        url = normalize_url(raw)
        if not url:
            raise _Fatal("target-rejected", "invalid URL")
        try:
            check_url(url)
        except URLSafetyError as exc:
            raise _Fatal("target-rejected", str(exc)) from exc
        ctx["entry_url"] = url
        await self.repo.update_audit(aid, target_url=url)

    async def _fetch_entry(self, aid: str, ctx: dict[str, Any]) -> None:
        url = ctx["entry_url"]
        fr = await self.fetcher.fetch(url)
        if fr.error in ("tls-handshake-failed", "unreachable") and url.startswith("https://"):
            alt = await self.fetcher.fetch("http://" + url[len("https://") :])
            if alt.error is None and alt.status is not None:
                fr = alt
                ctx["findings"].append(
                    registry.make_finding("https-unavailable", url=url, evidence=fr.final_url)
                )
        if fr.error or fr.status is None:
            raise _Fatal(fr.error or "unreachable", fr.error_detail or "")
        ctx["entry_fetch"] = fr
        final = fr.final_url
        from seoa.domain.urls import origin_of

        ctx["origin"] = origin_of(final)
        ctx["entry_final"] = final
        page = PageRecord(
            id=new_id(),
            url=url,
            final_url=final,
            status=fr.status,
            sample_kind="core",
            html_bytes=fr.html_bytes,
            ttfb_ms=fr.ttfb_ms,
        )
        ctx["pages"] = {url: page}
        ctx["fetches"] = {url: fr}
        if fr.html:
            await self.repo.store_body(aid, page.id, fr.html)
        await self.repo.add_page(aid, page)
        await self.repo.update_audit(aid, final_origin=ctx["origin"])
        await self._emit(aid, stage=Stage.FETCH_ENTRY, pages_fetched=1, pages_planned=1)

    async def _robots(self, aid: str, ctx: dict[str, Any]) -> None:
        res = await self.ops.run_robots(
            ctx["origin"], ctx["entry_url"], self.fetcher, self.s.bot_name
        )
        ctx["robots"] = res
        ctx["findings"] += res.findings
        ctx["not_checked"] += res.not_checked

    async def _discovery(self, aid: str, ctx: dict[str, Any]) -> None:
        robots = ctx["robots"]
        sm = await self.ops.discover_sitemaps(ctx["origin"], self.fetcher, robots.sitemaps)
        ctx["findings"] += sm.findings
        ctx["not_checked"] += sm.not_checked
        cands: dict[str, Candidate] = {}
        for u in sm.urls:
            n = normalize_url(u.loc)
            if n:
                cands[n] = Candidate(n, lastmod=u.lastmod, in_sitemap=True)
        fr = ctx["entry_fetch"]
        if fr.html:
            parsed = self.ops.parse(fr.html, ctx["entry_final"])
            for ln in parsed.links:
                n = normalize_url(ln.resolved) if ln.resolved else None
                if n and n not in cands:
                    cands[n] = Candidate(n, linked=True)
        ctx["candidates"] = list(cands.values())
        ctx["sitemap_urls_found"] = len(sm.urls)
        ctx["sitemap_set"] = {n for u in sm.urls if (n := normalize_url(u.loc))}
        await self._emit(
            aid, stage=Stage.DISCOVERY, message_key="discovery.found", pages_planned=len(cands)
        )

    async def _sample(self, aid: str, ctx: dict[str, Any]) -> None:
        from urllib.parse import urlparse

        host = urlparse(ctx["origin"]).hostname or ""
        robots = ctx["robots"]
        skipped: dict[str, int] = defaultdict(int)
        usable: list[Candidate] = []
        for c in ctx["candidates"]:
            if not in_scope(c.url, host):
                skipped["out_of_scope"] += 1
            elif not is_crawlable_page(c.url):
                skipped["not_a_page"] += 1
            elif not self.ops.robots_allows(robots, self.s.bot_name, c.url):
                skipped["robots"] += 1
            else:
                usable.append(c)
        n = int(ctx["opts"].get("max_pages") or self.s.max_pages_default)
        n = max(1, min(n, self.s.max_pages_cap))
        extra = [
            u
            for u in (normalize_url(x) for x in ctx["opts"].get("extra_urls", [])[:20])
            if u and in_scope(u, host)
        ]
        seed = int(ctx["opts"].get("_seed") or zlib.crc32(aid.encode()))
        sample, stats = select_sample(usable, n=n, seed=seed, mandatory=[ctx["entry_url"], *extra])
        ctx["sample"] = sample
        ctx["coverage"] = {
            "pages_discovered": len(ctx["candidates"]) + 1,
            "pages_planned": len(sample),
            "pages_fetched": 0,
            "pages_rendered": 0,
            "sitemap_urls": ctx.get("sitemap_urls_found", 0),
            "templates": [
                {"key": k, **v}
                for k, v in sorted(stats.items(), key=lambda kv: -kv[1]["discovered"])
            ][:30],
            "skipped": dict(skipped),
        }
        await self.repo.update_audit(aid, coverage=ctx["coverage"])
        await self._emit(
            aid, stage=Stage.SAMPLE, message_key="sample.selected", pages_planned=len(sample)
        )

    async def _fetch_pages(self, aid: str, ctx: dict[str, Any]) -> None:
        sample = [s for s in ctx["sample"] if s.url != ctx["entry_url"]]
        planned = len(ctx["sample"])
        done = {"n": 1}
        sem = asyncio.Semaphore(6)
        entry_tpl = next((s for s in ctx["sample"] if s.url == ctx["entry_url"]), None)
        if entry_tpl:
            ctx["pages"][ctx["entry_url"]].template_key = entry_tpl.template_key
            await self.repo.update_page(
                ctx["pages"][ctx["entry_url"]].id, template_key=entry_tpl.template_key
            )

        async def one(s: Any) -> None:
            async with sem:
                if await self.repo.is_cancel_requested(aid):
                    return
                fr = await self.fetcher.fetch(s.url)
                page = PageRecord(
                    id=new_id(),
                    url=s.url,
                    final_url=fr.final_url,
                    status=fr.status,
                    sample_kind=s.sample_kind,
                    template_key=s.template_key,
                    html_bytes=fr.html_bytes,
                    ttfb_ms=fr.ttfb_ms,
                    error=fr.error,
                )
                if fr.html:
                    await self.repo.store_body(aid, page.id, fr.html)
                ctx["pages"][s.url] = page
                ctx["fetches"][s.url] = fr
                await self.repo.add_page(aid, page)
                done["n"] += 1
                await self._emit(
                    aid,
                    stage=Stage.FETCH_PAGES,
                    message_key="fetch.page",
                    pages_fetched=done["n"],
                    pages_planned=planned,
                )

        await asyncio.gather(*(one(s) for s in sample))
        await self._check_cancel(aid)
        fetched = sum(1 for p in ctx["pages"].values() if p.error is None and p.status is not None)
        ctx["coverage"]["pages_fetched"] = fetched
        if fetched < planned:
            ctx["partial_reasons"].append("partial-sample")
        await self.repo.update_audit(aid, coverage=ctx["coverage"])

    async def _render(self, aid: str, ctx: dict[str, Any]) -> None:
        budget = 5
        rendered = 0
        order = [ctx["entry_url"]] + [u for u in ctx["pages"] if u != ctx["entry_url"]]
        for url in order:
            fr = ctx["fetches"].get(url)
            page = ctx["pages"].get(url)
            if not fr or not _html_ok(fr) or rendered >= budget:
                continue
            spa = self.ops.is_spa(fr.html)
            await self.repo.update_page(page.id, is_spa=int(spa))
            page.is_spa = spa
            if not spa:
                continue
            res = await self.ops.render(self.renderer, page.final_url or url)
            if res.error or not res.html:
                ctx["not_checked"].append(
                    NotChecked(
                        check_id="js-dependent-content", reason_code="render-failed", url=url
                    )
                )
                continue
            rendered += 1
            gap = self.ops.js_gap(fr.html or "", res.html)
            await self.repo.store_body(aid, page.id, res.html, kind="rendered")
            ctx.setdefault("rendered", {})[url] = res.html
            page.rendered = True
            page.js_gap = gap
            await self.repo.update_page(page.id, rendered=1, js_gap=gap)
        if "coverage" in ctx:
            ctx["coverage"]["pages_rendered"] = rendered
            await self.repo.update_audit(aid, coverage=ctx["coverage"])

        # lab performance (belge 11 s.3.2): entry on desktop and mobile, a few more pages on desktop
        targets: list[tuple[str, str]] = [
            (ctx["entry_url"], "desktop"),
            (ctx["entry_url"], "mobile"),
        ]
        others = [u for u, p in ctx["pages"].items() if u != ctx["entry_url"] and p.status == 200]
        targets += [(u, "desktop") for u in others[:2]]
        perfs = await self.ops.measure_perf(self.renderer, targets)
        usable = [p for p in perfs if not p.error]
        ctx["perf_all"] = perfs
        ctx["perf"] = usable
        await self.repo.save_blob(aid, "perf", perfs)

    async def _measure(self, aid: str, ctx: dict[str, Any]) -> None:
        pages: dict[str, PageRecord] = ctx["pages"]
        findings: list[Finding] = ctx["findings"]
        not_checked: list[NotChecked] = ctx["not_checked"]
        entry_fr = ctx["entry_fetch"]
        entry_html = ctx.get("rendered", {}).get(ctx["entry_url"]) or entry_fr.html or ""
        entry_parsed = self.ops.parse(entry_html, ctx["entry_final"]) if entry_html else None
        lang = detect_lang(
            getattr(entry_parsed, "lang", None) or None,
            getattr(entry_parsed, "main_text", "") or entry_html[:3000],
        )
        ctx["lang"] = lang
        btype = detect_business_type(
            entry_html, [ln.href for ln in entry_parsed.links] if entry_parsed else []
        )
        await self.repo.update_audit(aid, lang=lang, business_type=btype)

        titles: dict[str, list[str]] = defaultdict(list)
        descs: dict[str, list[str]] = defaultdict(list)
        parsed_cache: dict[str, Any] = {}
        for url, page in pages.items():
            fr = ctx["fetches"][url]
            if fr.status is not None and fr.status >= 500:
                findings.append(
                    registry.make_finding("page-status-5xx", url=url, evidence=str(fr.status))
                )
            elif fr.status is not None and fr.status >= 400:
                findings.append(
                    registry.make_finding("page-status-4xx", url=url, evidence=str(fr.status))
                )
            if len(fr.redirect_chain) >= 2:
                findings.append(
                    registry.make_finding(
                        "redirect-chain-long",
                        url=url,
                        evidence=" > ".join(h.url for h in fr.redirect_chain)[:200],
                        count=len(fr.redirect_chain),
                    )
                )
            if fr.ttfb_ms is not None and fr.ttfb_ms > 1800:
                findings.append(
                    registry.make_finding("slow-ttfb", url=url, evidence=f"{fr.ttfb_ms} ms")
                )
            html = ctx.get("rendered", {}).get(url) or fr.html
            if not html or not _html_ok(fr) or fr.status >= 400:
                continue
            parsed = self.ops.parse(html, fr.final_url)
            parsed_cache[url] = parsed
            out = self.ops.run_page_checks(fr, parsed, lang)
            sch = self.ops.run_schema_checks(parsed, url)
            for o in (out, sch):
                for f in o.findings:
                    findings.append(f.model_copy(update={"url": f.url or url}))
                not_checked += [n.model_copy(update={"url": n.url or url}) for n in o.not_checked]
            page.title = parsed.title or None
            page.word_count = parsed.word_count
            await self.repo.update_page(page.id, title=page.title, word_count=page.word_count)
            if parsed.title:
                titles[parsed.title.strip().lower()].append(url)
            if parsed.meta_description:
                descs[parsed.meta_description.strip().lower()].append(url)
            gap = page.js_gap or {}
            if page.rendered and gap.get("gap") is True:
                findings.append(
                    registry.make_finding(
                        "js-dependent-content",
                        url=url,
                        evidence="; ".join(self.ops.js_gap_reasons(gap))[:200],
                    )
                )
        for same, check in ((titles, "duplicate-title"), (descs, "duplicate-meta-description")):
            for text, urls in same.items():
                if len(urls) > 1:
                    for u in urls:
                        findings.append(
                            registry.make_finding(
                                check, url=u, evidence=text[:120], count=len(urls)
                            )
                        )

        tr = await self.ops.run_transport(ctx["entry_url"], entry_fr, self.fetcher)
        findings += tr.findings
        not_checked += tr.not_checked
        ctx["parsed"] = parsed_cache
        # Persist measurement output (append-only)
        await self.repo.add_findings(aid, findings)
        await self.repo.add_not_checked(aid, not_checked)

    async def _analyze(self, aid: str, ctx: dict[str, Any]) -> None:
        """Deep analysis: link graph, indexability table, duplicate content, visibility signals."""
        pages = self.ops.analysis_pages(ctx)
        vis_task: asyncio.Task[Any] | None = None
        if (
            self.s.visibility_enabled
        ):  # public lookups are slow: run them alongside the other analyses
            from urllib.parse import urlparse

            vis_task = asyncio.create_task(
                self.ops.collect_visibility(urlparse(ctx["origin"]).hostname or "")
            )
        psi_task: asyncio.Task[Any] | None = None
        crux_task: asyncio.Task[Any] | None = None
        if (
            self.ops.google_api_key()
        ):  # one key serves PageSpeed and CrUX; both are slow, so run alongside
            psi_task = asyncio.create_task(self.ops.run_psi(ctx["entry_url"]))
            crux_task = asyncio.create_task(self.ops.run_crux(ctx["entry_url"], ctx["origin"]))
        gsc_task: asyncio.Task[Any] | None = None
        if self.gsc_client is not None:
            from seoa.application.analysis.search_console.collector import collect_gsc

            gsc_task = asyncio.create_task(
                collect_gsc(
                    self.gsc_client,
                    entry_url=ctx["entry_url"],
                    sample_urls=[p.url for p in pages],
                    inspect_limit=self.s.gsc_inspect_limit,
                    keywords=ctx["opts"].get("keywords"),
                )
            )
        new_findings: list[Finding] = []
        new_nc: list[NotChecked] = []

        links = await self.ops.run_links(pages, ctx, self.fetcher, self.s)
        new_findings += links.output.findings
        new_nc += links.output.not_checked
        ctx["links"] = links.summary
        await self.repo.save_blob(aid, "links", links.summary)

        stats = {p.url: p for p in links.summary.pages}
        rows = self.ops.build_indexability(pages, ctx, stats, self.s)
        await self.repo.save_blob(aid, "indexability", rows)

        if ctx["mode"] == AuditMode.SITE:
            dup = self.ops.find_duplicates(pages)
            new_findings += dup.findings
            new_nc += dup.not_checked

        parsed = ctx.get("parsed", {})
        if parsed and not any(getattr(p, "schema_types", None) for p in parsed.values()):
            new_findings.append(registry.make_finding("schema-none-found", url=ctx["entry_url"]))
        ctx["has_schema"] = any(getattr(p, "schema_types", None) for p in parsed.values())
        ctx["has_images"] = any(getattr(p, "images", None) for p in parsed.values())

        await self._perf_findings(ctx, new_findings, new_nc)
        psi = None
        if psi_task is not None:
            try:
                psi = await psi_task
            except Exception as exc:  # optional source: never breaks the audit
                log.warning("psi failed: %s", type(exc).__name__)
        ctx["psi"] = psi is not None
        if psi is not None:
            new_findings += psi.findings
            new_nc += psi.not_checked
        field = None
        if crux_task is not None:
            try:
                field = await crux_task
            except Exception as exc:
                log.warning("crux failed: %s", type(exc).__name__)
        if field is not None:
            await self.repo.save_blob(aid, "field", field)
            ctx["field"] = field
            fc = self.ops.field_checks(field, ctx["entry_url"])
            new_findings += fc.findings
            got = {m.metric for m in field.metrics}
            # real-user data answers the checks lab data cannot (INP): they are no longer "not measured"
            new_nc += fc.not_checked

            def _answered(n: NotChecked) -> bool:
                return n.check_id.startswith("cwv-") and n.check_id.split("-")[1] in got

            new_nc[:] = [
                n
                for n in new_nc
                if not (_answered(n) and n.reason_code == "field-data-unavailable")
            ]
            ctx["not_checked"][:] = [n for n in ctx["not_checked"] if not _answered(n)]
        if "coverage" in ctx:
            ctx["coverage"]["psi"] = ctx["psi"]
            ctx["coverage"]["crux"] = bool(field is not None and field.metrics)
            await self.repo.update_audit(aid, coverage=ctx["coverage"])
        else:
            await self.repo.update_audit(
                aid, coverage={"psi": ctx["psi"], "crux": bool(field is not None and field.metrics)}
            )

        if gsc_task is not None:
            try:
                from seoa.application.analysis.search_console import collector as gsc_mod

                gsc_data = await gsc_task
                await self.repo.save_blob(aid, "gsc", gsc_data)
                gsc_out = gsc_mod.findings(gsc_data)
                new_findings += gsc_out.findings
                new_nc += gsc_out.not_checked
                if gsc_data.status == "ok":
                    ctx.setdefault("provided", set()).add("gsc")
                    ctx["gsc_ok"] = True
            except Exception as exc:  # optional source: never breaks the audit
                log.warning("gsc failed: %s", type(exc).__name__)

        if vis_task is not None:
            try:
                await self.repo.save_blob(aid, "visibility", await vis_task)
            except Exception as exc:  # informational: never breaks the audit
                log.warning("visibility failed: %s", type(exc).__name__)

        mod_findings, mod_nc, provided = await self._run_modules(aid, ctx, pages)
        new_findings += mod_findings
        new_nc += mod_nc
        ctx["provided"] = provided | ({"gsc"} if ctx.get("gsc_ok") else set())
        ctx["findings"] += new_findings
        ctx["not_checked"] += new_nc
        await self.repo.add_findings(aid, new_findings)
        await self.repo.add_not_checked(aid, new_nc)

    async def _run_modules(
        self, aid: str, ctx: dict[str, Any], pages: list[Any]
    ) -> tuple[list[Finding], list[NotChecked], set[str]]:
        """Run every registered analysis module concurrently; one that fails or times out is skipped."""
        from seoa.application.analysis.plugin import AnalysisInputs, modules

        entry_fr = ctx["entry_fetch"]
        entry_html = ctx.get("rendered", {}).get(ctx["entry_url"]) or entry_fr.html or ""

        async def save_file(name: str, data: bytes) -> str:
            return await self.repo.store_file(aid, name, data)

        inp = AnalysisInputs(
            audit_id=aid,
            mode=ctx["mode"],
            entry_url=ctx["entry_url"],
            origin=ctx["origin"],
            entry_fetch=entry_fr,
            entry_html=entry_html,
            entry_parsed=ctx.get("parsed", {}).get(ctx["entry_url"]),
            pages=pages,
            fetcher=self.fetcher,
            renderer=self.renderer,
            settings=self.s,
            lang=ctx.get("lang"),
            output_lang=ctx["opts"].get("lang", "tr"),
            options=dict(ctx["opts"]),
            robots=ctx.get("robots"),
            save_file=save_file,
            sitemap_urls=ctx.get("sitemap_set", set()),
            ops=self.ops,
        )
        mods = modules()

        async def one(m: Any) -> Any:
            try:
                return await asyncio.wait_for(m.run(inp), timeout=m.timeout_s)
            except Exception as exc:  # isolation: a module never breaks the audit
                log.warning("module %s failed: %s", m.name, type(exc).__name__)
                return None

        findings: list[Finding] = []
        nc: list[NotChecked] = []
        provided: set[str] = set()
        for res in await asyncio.gather(*(one(m) for m in mods)):
            if res is None:
                continue
            if res.data is not None:
                await self.repo.save_blob(aid, res.kind, res.data)
            findings += res.findings
            nc += res.not_checked
            provided |= res.available
        return findings, nc, provided

    async def _perf_findings(
        self, ctx: dict[str, Any], findings: list[Finding], nc: list[NotChecked]
    ) -> None:
        perfs = ctx.get("perf_all")
        if not perfs:
            return
        out = self.ops.perf_checks(perfs)
        findings += out.findings
        nc += out.not_checked

    async def _score(self, aid: str, ctx: dict[str, Any]) -> None:
        pages = list(ctx["pages"].values())
        parsed_ok = bool(ctx.get("parsed"))
        robots = ctx["robots"]
        has_lab = bool(ctx.get("perf"))
        measured: dict[Category, str | None] = {
            Category.TECHNICAL: None,
            Category.ONPAGE: None if parsed_ok else "no-html",
            Category.CONTENT: None if parsed_ok else "no-html",
            Category.SCHEMA: None
            if ctx.get("has_schema")
            else ("no-structured-data" if parsed_ok else "no-html"),
            Category.IMAGES: None
            if ctx.get("has_images")
            else ("no-images" if parsed_ok else "no-html"),
            Category.AI_READINESS: None if robots.available else "robots-unreachable",
            Category.LINKS: None if ctx.get("links") is not None else "no-data",
            Category.PERFORMANCE: None if has_lab else "no-lab-data",
        }
        available = {"headers", "robots", "sitemap", "rendered"} | ({"lab"} if has_lab else set())
        available |= ctx.get("provided", set())
        fr = ctx["entry_fetch"]
        scores = compute_scores(
            ctx["findings"],
            ctx["not_checked"],
            mode=ctx["mode"],
            pages=pages,
            measured=measured,
            gate_inputs=GateInputs(entry_url=ctx["entry_url"], entry_status=fr.status),
            available=available,
        )
        by_url: dict[str, list[Finding]] = defaultdict(list)
        for f in ctx["findings"]:
            if f.url:
                by_url[f.url].append(f)
        cats = [
            c.category
            for c in scores.categories
            if c.measured
            and c.category
            in (
                Category.ONPAGE,
                Category.CONTENT,
                Category.TECHNICAL,
                Category.SCHEMA,
                Category.IMAGES,
            )
        ]
        for p in pages:
            if p.error is None and p.status is not None and cats:
                p.page_score = page_score(by_url.get(p.url, []), cats)
                await self.repo.update_page(p.id, page_score=p.page_score)
        ctx["scores"] = scores
        await self.repo.save_scores(aid, scores)

    # ------------------------------------------------------------------ layer C

    def _top_findings(self, ctx: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
        by_id: dict[str, dict[str, Any]] = {}
        order = {s: i for i, s in enumerate(SEVERITY_ORDER)}
        for f in ctx["findings"]:
            e = by_id.setdefault(
                f.id,
                {
                    "id": f.id,
                    "severity": f.severity.value,
                    "category": f.category.value,
                    "message": f.message,
                    "evidence": f.evidence,
                    "url": f.url,
                    "pages": set(),
                },
            )
            if f.url:
                e["pages"].add(f.url)
        gate = ctx["scores"].gate.check_id if ctx["scores"].gate else None
        rows = sorted(
            by_id.values(),
            key=lambda e: (
                e["id"] != gate,
                order[Severity(e["severity"])],
                -len(e["pages"]),
                e["id"],
            ),
        )
        lang = ctx["opts"].get("lang", "tr")
        return [
            {
                **{k: v for k, v in e.items() if k != "pages"},
                "category_label": self.ops.category_label(e["category"], lang),
                "pages_affected": len(e["pages"]),
            }
            for e in rows[:limit]
        ]

    async def _advise(self, aid: str, ctx: dict[str, Any]) -> None:
        try:
            records = await self.ops.run_advisory(self.llm, ctx, self.s, aid)
        except Exception as exc:  # LLM failure never breaks the deterministic report
            log.warning("advise failed: %s", type(exc).__name__)
            ctx["partial_reasons"].append("llm-unavailable")
            return
        for r in records:
            await self.repo.add_advisory(aid, r)
            if r.error:
                ctx["partial_reasons"].append("llm-partial")
        ctx["cost"] = await self.ops.llm_cost(self.llm, aid)

    async def _synthesize(self, aid: str, ctx: dict[str, Any]) -> None:
        try:
            syn, advice = await self.ops.run_synthesis(
                self.llm, ctx, self._top_findings(ctx), ctx["opts"].get("lang", "tr"), aid
            )
        except Exception as exc:
            log.warning("synthesis failed: %s", type(exc).__name__)
            ctx["partial_reasons"].append("llm-unavailable")
            return
        await self.repo.save_synthesis(aid, syn)
        await self.repo.add_advice(aid, advice)
        ctx["cost"] = await self.ops.llm_cost(self.llm, aid)

    async def _report(self, aid: str, ctx: dict[str, Any]) -> None:
        """Final quality gate: the stored record must build a valid report."""
        rec = await self.repo.load_record(aid)
        if rec is None:
            raise RuntimeError("record vanished")
        await self.ops.validate_report(rec)
