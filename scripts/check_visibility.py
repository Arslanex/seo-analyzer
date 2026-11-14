"""Manual real-network check of the visibility signals: scripts/check_visibility.py example.com ..."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seoa.infrastructure.integrations.visibility import collect_visibility  # noqa: E402


async def main(domains: list[str]) -> int:
    for d in domains:
        v = await collect_visibility(d)
        print(f"== {d}")
        print(json.dumps(v.model_dump(mode="json"), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    args = sys.argv[1:] or ["example.com"]
    raise SystemExit(asyncio.run(main(args)))
