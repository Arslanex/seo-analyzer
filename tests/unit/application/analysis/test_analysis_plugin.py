"""The module framework: isolation, timeouts, storage and scoring requirements."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from seoa.application.analysis import plugin
from seoa.application.analysis.plugin import AnalysisInputs, ModuleResult, register_module
from seoa.application.audit.service import LocalAuditService
from seoa.bootstrap import build_local_service
from seoa.config import Settings
from seoa.domain import AuditMode, AuditStatus
from tests.e2e.site import BASE, build
from tests.support.fixture_fetcher import FixtureFetcher


class Block(BaseModel):
    value: int


class Good:
    name, kind, timeout_s = "t-good", "t_good", 5.0

    async def run(self, inp: AnalysisInputs) -> ModuleResult:
        await inp.save_file("shot.png", b"\x89PNG")
        return ModuleResult(kind=self.kind, data=Block(value=7), available={"gsc"})


class Crashes:
    name, kind, timeout_s = "t-crash", "t_crash", 5.0

    async def run(self, inp: AnalysisInputs) -> ModuleResult:
        raise RuntimeError("boom")


class Hangs:
    name, kind, timeout_s = "t-hang", "t_hang", 0.2

    async def run(self, inp: AnalysisInputs) -> ModuleResult:
        import asyncio

        await asyncio.sleep(5)
        return ModuleResult(kind=self.kind)


@pytest.fixture
async def svc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from seoa.domain import CheckOutput
    from seoa.infrastructure import adapters

    async def no_transport(entry_url, fr, fetcher):  # noqa: ANN001
        return CheckOutput()

    monkeypatch.setattr(adapters, "run_transport", no_transport)
    for m in (Good(), Crashes(), Hangs()):
        register_module(m)
    s = build_local_service(
        Settings(
            data_dir=tmp_path,
            render_enabled=False,
            visibility_enabled=False,
            anthropic_api_key=None,
            request_delay_s=0.0,
        ),
        fetcher=FixtureFetcher(build()),
        workers=1,
    )
    await s.start()
    yield s
    await s.stop()
    for name in ("t-good", "t-crash", "t-hang"):
        plugin._MODULES.pop(name, None)


async def test_modules_are_isolated_stored_and_provide_requirements(svc: LocalAuditService) -> None:
    aid = await svc.create_audit(f"{BASE}/hakkimizda", AuditMode.PAGE, enable_llm=False)
    async for _ in svc.events(aid):
        pass
    rec = await svc.get_audit(aid)
    assert (
        rec and rec.status == AuditStatus.COMPLETED
    )  # a crashing and a hanging module did not break it
    assert rec.extras["t_good"] == {"value": 7}
    assert "t_crash" not in rec.extras and "t_hang" not in rec.extras
    assert svc.repo.file_path(aid, "shot.png") is not None  # binary artefact stored under the audit
    assert svc.repo.file_path(aid, "../../etc/passwd") is None  # no path traversal
