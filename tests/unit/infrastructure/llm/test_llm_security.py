"""The API key must never be written anywhere in the repository or the data directory."""

from __future__ import annotations

from pathlib import Path

from seoa.config import ROOT, get_settings

SKIP_DIRS = {
    ".venv",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "node_modules",
}
SKIP_FILES = {".env"}


def test_api_key_value_appears_in_no_repo_or_data_file() -> None:
    key = get_settings().anthropic_api_key
    if not key or len(key) < 20:
        return  # nothing to leak
    needle = key.encode()
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.name in SKIP_FILES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.stat().st_size > 20_000_000:
            continue
        assert needle not in path.read_bytes(), f"API key found in {path}"


def test_env_file_is_gitignored() -> None:
    gi = Path(ROOT / ".gitignore").read_text()
    assert ".env" in gi.splitlines()
