"""Settings. The .env file is read from the project root; secrets are never logged."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _f(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _i(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("SEOA_DATA_DIR", ROOT / "data"))
    )
    anthropic_api_key: str | None = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY"), repr=False
    )
    llm_model: str = field(
        default_factory=lambda: os.environ.get("SEOA_LLM_MODEL", "claude-haiku-5-5")
    )
    llm_effort: str = field(default_factory=lambda: os.environ.get("SEOA_LLM_EFFORT", "low"))
    # Hard cap for ALL LLM spend through this installation (USD). User limit is 10.
    llm_budget_usd: float = field(default_factory=lambda: _f("SEOA_LLM_BUDGET_USD", 8.0))
    llm_max_pages: int = field(default_factory=lambda: _i("SEOA_LLM_MAX_PAGES", 3))
    bot_name: str = field(
        default_factory=lambda: os.environ.get("SEOA_BOT_NAME", "SEOAnalyzerBot/0.1")
    )
    bot_info_url: str = field(
        default_factory=lambda: os.environ.get("SEOA_BOT_INFO_URL", "https://example.invalid/bot")
    )
    max_pages_default: int = field(default_factory=lambda: _i("SEOA_MAX_PAGES", 25))
    max_pages_cap: int = field(default_factory=lambda: _i("SEOA_MAX_PAGES_CAP", 200))
    fetch_timeout_s: float = field(default_factory=lambda: _f("SEOA_FETCH_TIMEOUT_S", 20.0))
    per_host_concurrency: int = field(default_factory=lambda: _i("SEOA_PER_HOST_CONCURRENCY", 2))
    request_delay_s: float = field(default_factory=lambda: _f("SEOA_REQUEST_DELAY_S", 0.4))
    render_enabled: bool = field(default_factory=lambda: os.environ.get("SEOA_RENDER", "1") == "1")
    visibility_enabled: bool = field(
        default_factory=lambda: os.environ.get("SEOA_VISIBILITY", "1") == "1"
    )
    max_external_link_checks: int = field(
        default_factory=lambda: _i("SEOA_EXTERNAL_LINK_CHECKS", 40)
    )
    # Search Console (belge 11): OAuth client JSON; None -> <data_dir>/google_client.json
    google_client_file: Path | None = field(
        default_factory=lambda: (
            Path(v) if (v := os.environ.get("SEOA_GOOGLE_CLIENT_FILE")) else None
        )
    )
    # OpenPageRank (belge 12 B2): free key from keywordseverywhere.com/account/openpagerank; empty -> authority is "not measured"
    openpagerank_key: str | None = field(
        default_factory=lambda: os.environ.get("SEOA_OPENPAGERANK_KEY") or None, repr=False
    )
    # URL Inspection quota is 2000/day per property: keep the per-audit use small
    gsc_inspect_limit: int = field(default_factory=lambda: _i("SEOA_GSC_INSPECT_LIMIT", 10))

    @property
    def google_client_path(self) -> Path:
        return self.google_client_file or self.data_dir / "google_client.json"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "seoa.sqlite"


def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
