"""Request models and the input parsers shared by the JSON API and the HTML form."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from seoa.domain import AuditMode
from seoa.domain.text import clean_text

MAX_URL = 2048


MAX_KEYWORDS = 10


MAX_KEYWORD_LEN = 80


MAX_COMPETITORS = 3


def normalize_url(raw: str) -> str:
    """Syntax-only normalisation. SSRF policy is the fetcher's job, never the API's."""
    url = raw.strip()
    if not url:
        raise ValueError("empty")
    if len(url) > MAX_URL:
        raise ValueError("too_long")
    if any(ord(c) < 33 or ord(c) == 127 for c in url):
        raise ValueError("invalid_characters")
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("unsupported_scheme")
    if not parsed.hostname:
        raise ValueError("missing_host")
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise ValueError("userinfo_not_allowed")
    try:
        parsed.port  # noqa: B018 - validates the port
    except ValueError as exc:
        raise ValueError("invalid_port") from exc
    return parsed._replace(fragment="").geturl()


def parse_keywords(raw: str | list[str]) -> list[str]:
    """Comma- or newline-separated keywords (or a list): trimmed, de-duplicated, at most 10."""
    items = re.split(r"[,\n\r]+", raw) if isinstance(raw, str) else list(raw)
    out: list[str] = []
    for item in items:
        k = " ".join(clean_text(item).split())
        if not k:
            continue
        if len(k) > MAX_KEYWORD_LEN:
            raise ValueError("invalid_keywords")
        if k.casefold() not in {x.casefold() for x in out}:
            out.append(k)
    if len(out) > MAX_KEYWORDS:
        raise ValueError("too_many_keywords")
    return out


def parse_competitors(raw: str | list[str]) -> list[str]:
    """One address per line (or a list): syntax-normalised like the main URL, at most 3."""
    items = re.split(r"[\n\r,\s]+", raw) if isinstance(raw, str) else list(raw)
    out: list[str] = []
    for item in items:
        if not item.strip():
            continue
        try:
            url = normalize_url(item)
        except ValueError:
            raise ValueError("invalid_competitor") from None
        if url not in out:
            out.append(url)
    if len(out) > MAX_COMPETITORS:
        raise ValueError("too_many_competitors")
    return out


class CreateAuditRequest(BaseModel):
    url: str
    mode: AuditMode = AuditMode.SITE
    max_pages: int | None = Field(default=None, ge=1, le=200)
    enable_llm: bool = True
    lang: str = Field(default="tr", pattern="^(tr|en)$")
    keywords: list[str] = Field(default_factory=list, max_length=MAX_KEYWORDS)
    competitors: list[str] = Field(default_factory=list, max_length=MAX_COMPETITORS)

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        return normalize_url(v)

    @field_validator("keywords")
    @classmethod
    def _keywords(cls, v: list[str]) -> list[str]:
        return parse_keywords(v)

    @field_validator("competitors")
    @classmethod
    def _competitors(cls, v: list[str]) -> list[str]:
        return parse_competitors(v)


class RerunRequest(BaseModel):
    modules: list[str] = Field(min_length=1, max_length=6)

    @field_validator("modules")
    @classmethod
    def _modules(cls, v: list[str]) -> list[str]:
        for m in v:
            if not m or len(m) > 32 or not all(c.islower() or c == "_" for c in m):
                raise ValueError("invalid_module")
        return v


class QARequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)

    @field_validator("question")
    @classmethod
    def _q(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("empty")
        return v
