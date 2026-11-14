"""Async repository over SQLite. One connection, writes serialised by a lock."""

from __future__ import annotations

import asyncio
import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiosqlite

from seoa.application.audit.protocol import AuditEvent, AuditSummary
from seoa.domain import (
    AdviceRecord,
    AdvisoryRecord,
    AuditMode,
    AuditRecord,
    AuditStatus,
    FieldData,
    Finding,
    GscData,
    IndexabilityRow,
    LinkSummary,
    NotChecked,
    PagePerf,
    PageRecord,
    Scores,
    Stage,
    StageRecord,
    StageStatus,
    SynthesisRecord,
    VisibilitySignals,
)
from seoa.domain.ids import new_id
from seoa.infrastructure.persistence.schema import SCHEMA


def _bare_host(value: str) -> str:
    """Lower-case host of a URL or bare host, without ``www.``."""
    v = value.strip().lower()
    host = urlparse(v if "://" in v else f"//{v}").hostname or ""
    return host[4:] if host.startswith("www.") else host


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Repo:
    def __init__(self, db_path: Path, objects_dir: Path) -> None:
        self.db_path = db_path
        self.objects_dir = objects_dir
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self._seq: dict[str, int] = {}

    async def open(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._migrate()
        await self._db.commit()

    async def _migrate(self) -> None:
        """Rebuild audit_data without the old CHECK constraint (it rejected the newer kinds)."""
        async with self.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='audit_data'"
        ) as c:
            row = await c.fetchone()
        if row and row[0] and "CHECK (kind IN" in row[0]:
            await self.db.executescript(
                """
                ALTER TABLE audit_data RENAME TO audit_data_old;
                CREATE TABLE audit_data (
                  audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
                  kind TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (audit_id, kind));
                INSERT INTO audit_data SELECT audit_id, kind, data FROM audit_data_old;
                DROP TABLE audit_data_old;
                """
            )

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Repo.open() not called"
        return self._db

    async def _exec(self, sql: str, args: tuple[Any, ...] = ()) -> None:
        async with self._lock:
            await self.db.execute(sql, args)
            await self.db.commit()

    # ------------------------------------------------------------------ audits

    async def create_audit(
        self,
        *,
        url: str,
        mode: AuditMode,
        options: dict[str, Any],
        seed: int,
        parent: str | None = None,
        budget: dict[str, Any] | None = None,
    ) -> str:
        aid = new_id()
        await self._exec(
            "INSERT INTO audits (id, mode, target_url, status, created_at, sample_seed, options, parent_audit_id, budget)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                aid,
                mode.value,
                url,
                AuditStatus.QUEUED.value,
                _now(),
                seed,
                json.dumps(options),
                parent,
                json.dumps(budget or {}),
            ),
        )
        return aid

    async def update_audit(self, aid: str, **fields: Any) -> None:
        if not fields:
            return
        cols = []
        vals: list[Any] = []
        for k, v in fields.items():
            cols.append(f"{k}=?")
            vals.append(
                json.dumps(v)
                if isinstance(v, (dict, list))
                else (v.value if hasattr(v, "value") else v)
            )
        vals.append(aid)
        await self._exec(f"UPDATE audits SET {', '.join(cols)} WHERE id=?", tuple(vals))

    async def get_option(self, aid: str) -> dict[str, Any]:
        async with self.db.execute(
            "SELECT options, sample_seed, mode, target_url FROM audits WHERE id=?", (aid,)
        ) as c:
            row = await c.fetchone()
        if not row:
            return {}
        return {
            **json.loads(row["options"]),
            "_seed": row["sample_seed"],
            "_mode": row["mode"],
            "_url": row["target_url"],
        }

    async def request_cancel(self, aid: str) -> bool:
        async with self._lock:
            cur = await self.db.execute(
                "UPDATE audits SET cancel_requested=1 WHERE id=? AND status IN ('queued','running')",
                (aid,),
            )
            await self.db.commit()
            return cur.rowcount > 0

    async def is_cancel_requested(self, aid: str) -> bool:
        async with self.db.execute("SELECT cancel_requested FROM audits WHERE id=?", (aid,)) as c:
            row = await c.fetchone()
        return bool(row and row[0])

    async def set_stage(
        self, aid: str, stage: Stage, status: StageStatus, detail: str | None = None
    ) -> None:
        now = _now()
        async with self._lock:
            await self.db.execute(
                "INSERT INTO audit_stages (audit_id, stage, status, started_at, finished_at, detail) VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(audit_id, stage) DO UPDATE SET status=excluded.status,"
                " started_at=COALESCE(audit_stages.started_at, excluded.started_at),"
                " finished_at=CASE WHEN excluded.status IN ('done','skipped','failed') THEN excluded.finished_at ELSE audit_stages.finished_at END,"
                " detail=COALESCE(excluded.detail, audit_stages.detail)",
                (
                    aid,
                    stage.value,
                    status.value,
                    now if status == StageStatus.RUNNING else now,
                    now
                    if status in (StageStatus.DONE, StageStatus.SKIPPED, StageStatus.FAILED)
                    else None,
                    detail,
                ),
            )
            await self.db.commit()

    # ------------------------------------------------------------------ pages / bodies

    async def add_page(self, aid: str, page: PageRecord) -> None:
        await self._exec(
            "INSERT OR REPLACE INTO audit_pages (id, audit_id, url, final_url, status, sample_kind, template_key, html_bytes,"
            " ttfb_ms, error, rendered, is_spa, js_gap, title, word_count, page_score) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                page.id,
                aid,
                page.url,
                page.final_url,
                page.status,
                page.sample_kind,
                page.template_key,
                page.html_bytes,
                page.ttfb_ms,
                page.error,
                int(page.rendered),
                None if page.is_spa is None else int(page.is_spa),
                json.dumps(page.js_gap) if page.js_gap else None,
                page.title,
                page.word_count,
                page.page_score,
            ),
        )

    async def update_page(self, page_id: str, **fields: Any) -> None:
        cols, vals = [], []
        for k, v in fields.items():
            cols.append(f"{k}=?")
            vals.append(json.dumps(v) if isinstance(v, (dict, list)) else v)
        vals.append(page_id)
        await self._exec(f"UPDATE audit_pages SET {', '.join(cols)} WHERE id=?", tuple(vals))

    def _body_path(self, aid: str, page_id: str, kind: str) -> Path:
        return self.objects_dir / aid / f"{page_id}.{kind}.html.gz"

    async def store_body(self, aid: str, page_id: str, html: str, kind: str = "raw") -> str:
        path = self._body_path(aid, page_id, kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, gzip.compress(html.encode("utf-8", "replace")))
        return str(path)

    async def store_file(self, aid: str, name: str, data: bytes) -> str:
        """Binary artefact of an audit (screenshots). ``name`` must be a plain file name."""
        safe = "".join(c for c in name if c.isalnum() or c in "._-")[:80] or "file"
        path = self.objects_dir / aid / "files" / safe
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        return safe

    def file_path(self, aid: str, name: str) -> Path | None:
        safe = "".join(c for c in name if c.isalnum() or c in "._-")[:80]
        path = self.objects_dir / aid / "files" / safe
        return path if safe == name and path.is_file() else None

    async def load_body(self, aid: str, page_id: str, kind: str = "raw") -> str | None:
        path = self._body_path(aid, page_id, kind)
        if not path.exists():
            return None
        data = await asyncio.to_thread(path.read_bytes)
        return gzip.decompress(data).decode("utf-8", "replace")

    # ------------------------------------------------------------------ results

    async def add_findings(self, aid: str, findings: list[Finding]) -> None:
        if not findings:
            return
        async with self._lock:
            await self.db.executemany(
                "INSERT INTO findings (audit_id, check_id, severity, category, layer, url, data) VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        aid,
                        f.id,
                        f.severity.value,
                        f.category.value,
                        f.layer.value,
                        f.url,
                        f.model_dump_json(),
                    )
                    for f in findings
                ],
            )
            await self.db.commit()

    async def add_not_checked(self, aid: str, items: list[NotChecked]) -> None:
        if not items:
            return
        async with self._lock:
            await self.db.executemany(
                "INSERT INTO not_checked (audit_id, check_id, reason_code, url) VALUES (?,?,?,?)",
                [(aid, n.check_id, n.reason_code, n.url) for n in items],
            )
            await self.db.commit()

    async def add_advisory(self, aid: str, rec: AdvisoryRecord) -> None:
        await self._exec(
            "INSERT INTO advisory (audit_id, kind, page_url, data) VALUES (?,?,?,?)",
            (aid, rec.kind, rec.page_url, rec.model_dump_json()),
        )

    async def add_advice(self, aid: str, items: list[AdviceRecord]) -> None:
        async with self._lock:
            await self.db.executemany(
                "INSERT INTO advice (audit_id, finding_id, url, text) VALUES (?,?,?,?)",
                [(aid, a.finding_id, a.url, a.text) for a in items],
            )
            await self.db.commit()

    async def clear_layer_c(self, aid: str) -> None:
        async with self._lock:
            for t in ("advisory", "advice"):
                await self.db.execute(f"DELETE FROM {t} WHERE audit_id=?", (aid,))
            await self.db.execute("UPDATE audits SET synthesis=NULL WHERE id=?", (aid,))
            await self.db.commit()

    async def save_scores(self, aid: str, scores: Scores) -> None:
        await self._exec(
            "UPDATE audits SET scores=?, score_version=? WHERE id=?",
            (scores.model_dump_json(), scores.score_version, aid),
        )

    async def save_blob(self, aid: str, kind: str, payload: Any) -> None:
        """Persist a deep-analysis result (pydantic model or list of models) as JSON."""
        if isinstance(payload, list):
            data = json.dumps([p.model_dump(mode="json") for p in payload])
        elif isinstance(payload, dict):
            data = json.dumps(payload)
        else:
            data = payload.model_dump_json()
        await self._exec(
            "INSERT INTO audit_data (audit_id, kind, data) VALUES (?,?,?)"
            " ON CONFLICT(audit_id, kind) DO UPDATE SET data=excluded.data",
            (aid, kind, data),
        )

    async def save_synthesis(self, aid: str, syn: SynthesisRecord) -> None:
        await self._exec("UPDATE audits SET synthesis=? WHERE id=?", (syn.model_dump_json(), aid))

    async def add_qa(self, aid: str, question: str, answer: dict[str, Any]) -> None:
        await self._exec(
            "INSERT INTO qa (audit_id, question, answer, created_at) VALUES (?,?,?,?)",
            (aid, question, json.dumps(answer), _now()),
        )

    async def list_qa(self, aid: str, limit: int = 50) -> list[dict[str, Any]]:
        """Saved questions and answers of an audit, oldest first."""
        async with self.db.execute(
            "SELECT question, answer FROM qa WHERE audit_id=? ORDER BY id LIMIT ?", (aid, limit)
        ) as c:
            rows = await c.fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            try:
                ans = json.loads(r["answer"])
            except ValueError:
                continue
            if isinstance(ans, dict):
                out.append({"question": str(r["question"]), "answer": ans})
        return out

    async def count_qa(self, aid: str) -> int:
        async with self.db.execute("SELECT COUNT(*) FROM qa WHERE audit_id=?", (aid,)) as c:
            row = await c.fetchone()
        return int(row[0]) if row else 0

    # ------------------------------------------------------------------ events

    async def add_event(self, aid: str, ev: dict[str, Any]) -> AuditEvent:
        async with self._lock:
            if aid not in self._seq:
                async with self.db.execute(
                    "SELECT COALESCE(MAX(seq),0) FROM events WHERE audit_id=?", (aid,)
                ) as c:
                    row = await c.fetchone()
                self._seq[aid] = int(row[0]) if row else 0
            self._seq[aid] += 1
            event = AuditEvent(seq=self._seq[aid], audit_id=aid, ts=datetime.now(UTC), **ev)
            await self.db.execute(
                "INSERT INTO events (audit_id, seq, data) VALUES (?,?,?)",
                (aid, event.seq, event.model_dump_json()),
            )
            await self.db.commit()
        return event

    async def events_after(self, aid: str, after: int) -> list[AuditEvent]:
        async with self.db.execute(
            "SELECT data FROM events WHERE audit_id=? AND seq>? ORDER BY seq", (aid, after)
        ) as c:
            rows = await c.fetchall()
        return [AuditEvent.model_validate_json(r[0]) for r in rows]

    # ------------------------------------------------------------------ read

    async def load_record(self, aid: str) -> AuditRecord | None:
        async with self.db.execute("SELECT * FROM audits WHERE id=?", (aid,)) as c:
            a = await c.fetchone()
        if not a:
            return None

        async def q(sql: str) -> list[aiosqlite.Row]:
            async with self.db.execute(sql, (aid,)) as cur:
                return list(await cur.fetchall())

        stages = [
            StageRecord(
                stage=Stage(r["stage"]),
                status=StageStatus(r["status"]),
                started_at=r["started_at"],
                finished_at=r["finished_at"],
                detail=r["detail"],
            )
            for r in await q("SELECT * FROM audit_stages WHERE audit_id=? ORDER BY started_at")
        ]
        pages = [
            PageRecord(
                id=r["id"],
                url=r["url"],
                final_url=r["final_url"],
                status=r["status"],
                sample_kind=r["sample_kind"],
                template_key=r["template_key"],
                html_bytes=r["html_bytes"],
                ttfb_ms=r["ttfb_ms"],
                error=r["error"],
                rendered=bool(r["rendered"]),
                is_spa=None if r["is_spa"] is None else bool(r["is_spa"]),
                js_gap=json.loads(r["js_gap"]) if r["js_gap"] else None,
                title=r["title"],
                word_count=r["word_count"],
                page_score=r["page_score"],
            )
            for r in await q("SELECT * FROM audit_pages WHERE audit_id=? ORDER BY rowid")
        ]
        findings = [
            Finding.model_validate_json(r["data"])
            for r in await q("SELECT data FROM findings WHERE audit_id=? ORDER BY rowid_")
        ]
        nc = [
            NotChecked(check_id=r["check_id"], reason_code=r["reason_code"], url=r["url"])
            for r in await q("SELECT * FROM not_checked WHERE audit_id=?")
        ]
        adv = [
            AdvisoryRecord.model_validate_json(r["data"])
            for r in await q("SELECT data FROM advisory WHERE audit_id=?")
        ]
        advice = [
            AdviceRecord(finding_id=r["finding_id"], url=r["url"], text=r["text"])
            for r in await q("SELECT * FROM advice WHERE audit_id=?")
        ]
        return AuditRecord(
            id=a["id"],
            mode=AuditMode(a["mode"]),
            target_url=a["target_url"],
            final_origin=a["final_origin"],
            status=AuditStatus(a["status"]),
            business_type=a["business_type"],
            lang=a["lang"],
            created_at=a["created_at"],
            finished_at=a["finished_at"],
            rule_version=a["rule_version"],
            score_version=a["score_version"],
            parent_audit_id=a["parent_audit_id"],
            coverage=json.loads(a["coverage"]),
            budget=json.loads(a["budget"]),
            cost=json.loads(a["cost"]),
            stages=stages,
            pages=pages,
            findings=findings,
            not_checked=nc,
            scores=Scores.model_validate_json(a["scores"]) if a["scores"] else None,
            advisory=adv,
            advice=advice,
            **await self._load_blobs(aid),
            synthesis=SynthesisRecord.model_validate_json(a["synthesis"])
            if a["synthesis"]
            else None,
            error=a["error"],
        )

    async def _load_blobs(self, aid: str) -> dict[str, Any]:
        async with self.db.execute(
            "SELECT kind, data FROM audit_data WHERE audit_id=?", (aid,)
        ) as c:
            rows = {r["kind"]: r["data"] for r in await c.fetchall()}
        out: dict[str, Any] = {}
        if "links" in rows:
            out["links"] = LinkSummary.model_validate_json(rows["links"])
        if "perf" in rows:
            out["perf"] = [PagePerf.model_validate(x) for x in json.loads(rows["perf"])]
        if "indexability" in rows:
            out["indexability"] = [
                IndexabilityRow.model_validate(x) for x in json.loads(rows["indexability"])
            ]
        if "visibility" in rows:
            out["visibility"] = VisibilitySignals.model_validate_json(rows["visibility"])
        if "gsc" in rows:
            out["gsc"] = GscData.model_validate_json(rows["gsc"])
        if "field" in rows:
            out["field"] = FieldData.model_validate_json(rows["field"])
        known = {"links", "perf", "indexability", "visibility", "gsc", "field"}
        out["extras"] = {k: json.loads(v) for k, v in rows.items() if k not in known}
        return out

    @staticmethod
    def _summary(r: aiosqlite.Row) -> AuditSummary:
        sc = json.loads(r["scores"]) if r["scores"] else {}
        return AuditSummary(
            id=r["id"],
            target_url=r["target_url"],
            mode=AuditMode(r["mode"]),
            status=AuditStatus(r["status"]),
            overall=sc.get("overall"),
            coverage_pct=sc.get("coverage_pct"),
            created_at=r["created_at"],
        )

    async def list_summaries(self, limit: int = 20) -> list[AuditSummary]:
        async with self.db.execute(
            "SELECT id, target_url, mode, status, scores, created_at FROM audits ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as c:
            rows = await c.fetchall()
        return [self._summary(r) for r in rows]

    async def get_profile(self, url_or_host: str) -> dict[str, list[str]]:
        """Saved target keywords and competitors of a site (empty lists when none)."""
        host = _bare_host(url_or_host)
        empty: dict[str, list[str]] = {"keywords": [], "competitors": []}
        if not host:
            return empty
        async with self.db.execute(
            "SELECT keywords, competitors FROM site_profiles WHERE host = ?", (host,)
        ) as c:
            row = await c.fetchone()
        if row is None:
            return empty
        out = {}
        for key in ("keywords", "competitors"):
            try:
                val = json.loads(row[key])
            except ValueError:
                val = []
            out[key] = [str(x) for x in val] if isinstance(val, list) else []
        return out

    async def save_profile(
        self, url_or_host: str, keywords: list[str], competitors: list[str]
    ) -> None:
        """Remember the inputs for the site; empty lists clear them."""
        host = _bare_host(url_or_host)
        if not host:
            return
        await self._exec(
            "INSERT INTO site_profiles (host, keywords, competitors, updated_at)"
            " VALUES (?, ?, ?, ?) ON CONFLICT(host) DO UPDATE SET"
            " keywords = excluded.keywords, competitors = excluded.competitors,"
            " updated_at = excluded.updated_at",
            (host, json.dumps(keywords), json.dumps(competitors), _now()),
        )

    async def list_site_audits(self, host: str, limit: int = 20) -> list[AuditSummary]:
        """Audits whose target is on ``host`` (``www.`` ignored), newest first."""
        want = _bare_host(host)
        if not want:
            return []
        async with self.db.execute(
            "SELECT id, target_url, mode, status, scores, created_at FROM audits"
            " WHERE target_url LIKE ? ORDER BY created_at DESC LIMIT 500",
            (f"%{want}%",),
        ) as c:
            rows = await c.fetchall()
        # LIKE only narrows the candidates; the host match itself is exact
        out = [self._summary(r) for r in rows if _bare_host(r["target_url"]) == want]
        return out[:limit]

    async def clone_base(self, parent: str, child: str) -> dict[str, str]:
        """Copy pages, findings, not_checked, scores from ``parent`` into ``child`` (LLM-only rerun).

        Returns {parent_page_id: child_page_id}. Bodies are read from the parent's object dir.
        """
        mapping: dict[str, str] = {}
        async with self._lock:
            async with self.db.execute(
                "SELECT * FROM audit_pages WHERE audit_id=?", (parent,)
            ) as c:
                rows = await c.fetchall()
            for r in rows:
                nid = new_id()
                mapping[r["id"]] = nid
                d = dict(r)
                d["id"], d["audit_id"] = nid, child
                cols = ",".join(d)
                await self.db.execute(
                    f"INSERT INTO audit_pages ({cols}) VALUES ({','.join('?' * len(d))})",
                    tuple(d.values()),
                )
            for t, cols in (
                ("findings", "check_id, severity, category, layer, url, data"),
                ("not_checked", "check_id, reason_code, url"),
            ):
                await self.db.execute(
                    f"INSERT INTO {t} (audit_id, {cols}) SELECT ?, {cols} FROM {t} WHERE audit_id=?",
                    (child, parent),
                )
            await self.db.execute(
                "UPDATE audits SET scores=(SELECT scores FROM audits WHERE id=?),"
                " coverage=(SELECT coverage FROM audits WHERE id=?), final_origin=(SELECT final_origin FROM audits WHERE id=?),"
                " lang=(SELECT lang FROM audits WHERE id=?), business_type=(SELECT business_type FROM audits WHERE id=?) WHERE id=?",
                (parent, parent, parent, parent, parent, child),
            )
            await self.db.commit()
        return mapping

    async def get_status(self, aid: str) -> str | None:
        async with self.db.execute("SELECT status FROM audits WHERE id=?", (aid,)) as c:
            row = await c.fetchone()
        return row[0] if row else None

    async def list_by_status(self, *statuses: str) -> list[str]:
        marks = ",".join("?" * len(statuses))
        async with self.db.execute(
            f"SELECT id FROM audits WHERE status IN ({marks}) ORDER BY created_at", statuses
        ) as c:
            return [r[0] for r in await c.fetchall()]
