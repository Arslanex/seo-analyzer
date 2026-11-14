"""CLI: run one audit and print a short summary (and optionally write the HTML report)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seoa.bootstrap import build_local_service  # noqa: E402
from seoa.domain import AuditMode  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--mode", choices=["page", "site"], default="page")
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--lang", default="tr")
    ap.add_argument("--html", help="write the HTML report to this path")
    ns = ap.parse_args()
    svc = build_local_service()
    await svc.start()
    try:
        aid = await svc.create_audit(
            ns.url,
            AuditMode(ns.mode),
            max_pages=ns.max_pages,
            enable_llm=not ns.no_llm,
            lang=ns.lang,
        )
        async for ev in svc.events(aid):
            if ev.stage:
                print(
                    f"  [{ev.stage.value:11}] {getattr(ev.status, 'value', ev.status)} {ev.message_key}"
                    + (f" ({ev.pages_fetched}/{ev.pages_planned})" if ev.pages_planned else "")
                )
        rec = await svc.get_audit(aid)
        assert rec
        sc = rec.scores
        print(
            f"\nstatus={rec.status.value} overall={getattr(sc, 'overall', None)} coverage={getattr(sc, 'coverage_pct', None)} "
            f"findings={len(rec.findings)} pages={len(rec.pages)} error={rec.error}"
        )
        if ns.html:
            from seoa.application.reporting.builder import build_report
            from seoa.presentation.web.html import render_report_html

            Path(ns.html).write_text(
                render_report_html(build_report(rec, ns.lang), ns.lang), encoding="utf-8"
            )
            print("html ->", ns.html)
        print("spend:", await svc.spend())
        return 0 if rec.status.value in ("completed", "partial") else 1
    finally:
        await svc.stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
