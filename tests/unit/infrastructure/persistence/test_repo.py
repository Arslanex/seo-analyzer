from __future__ import annotations

from pathlib import Path

import pytest

from seoa.domain import (
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
from seoa.infrastructure.persistence import Repo


@pytest.fixture
async def repo(tmp_path: Path):
    r = Repo(tmp_path / "t.sqlite", tmp_path / "obj")
    await r.open()
    yield r
    await r.close()


async def test_roundtrip(repo: Repo) -> None:
    aid = await repo.create_audit(
        url="https://e.com/", mode=AuditMode.PAGE, options={"x": 1}, seed=5
    )
    await repo.update_audit(
        aid, status=AuditStatus.RUNNING, final_origin="https://e.com", coverage={"pages_fetched": 1}
    )
    await repo.set_stage(aid, Stage.VALIDATE, StageStatus.RUNNING)
    await repo.set_stage(aid, Stage.VALIDATE, StageStatus.DONE)
    await repo.add_page(aid, PageRecord(id="p1", url="https://e.com/", status=200, title="T"))
    await repo.add_findings(
        aid,
        [
            Finding(
                id="x",
                category=Category.ONPAGE,
                severity=Severity.LOW,
                message_key="k",
                message="m",
                url="https://e.com/",
            )
        ],
    )
    await repo.add_not_checked(aid, [NotChecked(check_id="y", reason_code="headers-unavailable")])
    rec = await repo.load_record(aid)
    assert rec and rec.status == AuditStatus.RUNNING and rec.coverage == {"pages_fetched": 1}
    assert rec.stages[0].status == StageStatus.DONE and rec.pages[0].title == "T"
    assert rec.findings[0].id == "x" and rec.not_checked[0].reason_code == "headers-unavailable"


async def test_events_are_sequenced_and_resumable(repo: Repo) -> None:
    aid = await repo.create_audit(url="https://e.com/", mode=AuditMode.SITE, options={}, seed=1)
    for i in range(3):
        await repo.add_event(aid, {"message_key": f"m{i}"})
    evs = await repo.events_after(aid, 1)
    assert [e.seq for e in evs] == [2, 3]


async def test_body_storage_is_gzipped_and_roundtrips(repo: Repo, tmp_path: Path) -> None:
    aid = await repo.create_audit(url="https://e.com/", mode=AuditMode.PAGE, options={}, seed=1)
    await repo.store_body(aid, "p1", "<p>Çok güzel ş</p>")
    assert await repo.load_body(aid, "p1") == "<p>Çok güzel ş</p>"
    assert await repo.load_body(aid, "nope") is None


async def test_cancel_only_while_active(repo: Repo) -> None:
    aid = await repo.create_audit(url="https://e.com/", mode=AuditMode.PAGE, options={}, seed=1)
    assert await repo.request_cancel(aid) is True and await repo.is_cancel_requested(aid)
    await repo.update_audit(aid, status=AuditStatus.COMPLETED)
    assert await repo.request_cancel(aid) is False


async def test_summaries(repo: Repo) -> None:
    await repo.create_audit(url="https://e.com/", mode=AuditMode.PAGE, options={}, seed=1)
    s = await repo.list_summaries()
    assert s[0].target_url == "https://e.com/" and s[0].overall is None


async def test_old_audit_data_check_constraint_is_migrated(tmp_path: Path) -> None:
    import aiosqlite

    from seoa.domain import FieldData

    path = tmp_path / "old.sqlite"
    async with aiosqlite.connect(path) as db:  # a database created by an earlier version
        await db.executescript(
            "CREATE TABLE audits (id TEXT PRIMARY KEY);"
            "CREATE TABLE audit_data (audit_id TEXT NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('links','perf','indexability','visibility')),"
            " data TEXT NOT NULL, PRIMARY KEY (audit_id, kind));"
            "INSERT INTO audits VALUES ('a1'); INSERT INTO audit_data VALUES ('a1','links','{}');"
        )
        await db.commit()
    r = Repo(path, tmp_path / "obj")
    await r.open()
    await r.save_blob("a1", "field", FieldData(error="no-data"))  # would violate the old CHECK
    async with r.db.execute("SELECT COUNT(*) FROM audit_data WHERE audit_id='a1'") as c:
        assert (await c.fetchone())[0] == 2  # the old row survived the migration
    await r.close()


async def test_site_profile_is_saved_per_host_and_can_be_cleared(repo: Repo) -> None:
    empty = {"keywords": [], "competitors": []}
    assert await repo.get_profile("https://e.com/") == empty
    await repo.save_profile("https://www.E.com/page", ["a b", "c"], ["https://r.com"])
    for same in ("e.com", "https://e.com/other", "www.e.com"):
        assert await repo.get_profile(same) == {
            "keywords": ["a b", "c"],
            "competitors": ["https://r.com"],
        }
    assert await repo.get_profile("sub.e.com") == empty  # a subdomain is another site
    await repo.save_profile("e.com", ["only"], [])
    assert await repo.get_profile("e.com") == {"keywords": ["only"], "competitors": []}
    await repo.save_profile("e.com", [], [])
    assert await repo.get_profile("e.com") == empty
    await repo.save_profile("", ["x"], [])  # no host: nothing is stored
    assert await repo.get_profile("") == empty
