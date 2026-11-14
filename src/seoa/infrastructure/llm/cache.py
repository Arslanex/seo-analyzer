"""Persistent LLM response cache (sqlite). Key = sha256(input + prompt_version + rubric_version + model)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

from seoa.config import get_settings


def cache_key(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


class LLMCache:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else get_settings().data_dir / "llm_cache.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, purpose TEXT, "
                "response TEXT NOT NULL, created_at REAL, hit_count INTEGER DEFAULT 0)"
            )

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def get(self, key: str) -> dict | None:  # type: ignore[type-arg]
        with self._conn() as c:
            row = c.execute("SELECT response FROM llm_cache WHERE key=?", (key,)).fetchone()
            if row is None:
                return None
            c.execute("UPDATE llm_cache SET hit_count=hit_count+1 WHERE key=?", (key,))
        return dict(json.loads(row[0]))

    def put(self, key: str, purpose: str, response: dict) -> None:  # type: ignore[type-arg]
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO llm_cache(key,purpose,response,created_at) VALUES (?,?,?,?)",
                (key, purpose, json.dumps(response, ensure_ascii=False), time.time()),
            )
