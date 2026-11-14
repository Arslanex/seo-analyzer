"""OpenPageRank integration and mod_authority (belge 12 B2). No real network."""

from __future__ import annotations

from types import SimpleNamespace

from seoa.application.analysis import plugin
from seoa.application.analysis.modules.authority import AuthorityModule
from seoa.infrastructure.integrations.openpagerank import (
    AuthoritySignal,
    fetch_authority,
    parse_response,
)
from tests.support.modules import inputs

KEY = "opr-secret-key-123"
OK = {
    "status_code": 200,
    "response": [
        {
            "status_code": 200,
            "page_rank_integer": 5,
            "page_rank_decimal": 5.43,
            "rank": "123456",
            "domain": "example.com",
        }
    ],
}


class _Body:
    def __init__(self, data: bytes) -> None:
        self._d = data

    async def iter_chunked(self, n: int):  # type: ignore[no-untyped-def]
        for i in range(0, len(self._d), n):
            yield self._d[i : i + n]


class _Resp:
    def __init__(self, status: int, data: bytes) -> None:
        self.status = status
        self.content = _Body(data)

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *a: object) -> None:
        return None


class FakeSession:
    def __init__(self, status: int = 200, body: bytes = b"") -> None:
        self.status, self.body = status, body
        self.calls: list[tuple[str, dict[str, str], bool]] = []

    def get(self, url: str, *, headers: dict[str, str], allow_redirects: bool) -> _Resp:
        self.calls.append((url, headers, allow_redirects))
        return _Resp(self.status, self.body)

    async def close(self) -> None:
        return None


def test_registered() -> None:
    assert "authority" in plugin.MODULE_FILES
    assert "authority" in {m.kind for m in plugin.modules()}


def test_parse_response() -> None:
    sig = parse_response(OK, "example.com")
    assert (sig.page_rank_decimal, sig.page_rank_integer, sig.rank) == (5.43, 5, 123456)
    assert parse_response({"response": [{"status_code": 404}]}, "x.com").error == "no-data"
    assert parse_response("nope", "x.com").error == "bad-json"
    assert parse_response({"response": []}, "x.com").error == "bad-json"


async def test_key_goes_in_the_header_only_and_domain_is_registrable() -> None:
    import json

    sess = FakeSession(200, json.dumps(OK).encode())
    sig = await fetch_authority("www.shop.example.com.tr", session=sess, key=KEY)
    (url, headers, redirects) = sess.calls[0]
    assert headers["API-OPR"] == KEY and KEY not in url and redirects is False
    assert "domains%5B%5D=example.com.tr" in url
    assert KEY not in sig.model_dump_json() and sig.page_rank_integer == 5


async def test_error_codes_never_carry_the_key() -> None:
    for status, code in (
        (401, "unauthorized"),
        (403, "unauthorized"),
        (429, "rate-limited"),
        (500, "http-500"),
    ):
        sig = await fetch_authority("example.com", session=FakeSession(status), key=KEY)
        assert sig.error == code and KEY not in sig.model_dump_json()
    big = await fetch_authority("example.com", session=FakeSession(200, b"x" * 200_000), key=KEY)
    assert big.error == "too-large"
    bad = await fetch_authority("example.com", session=FakeSession(200, b"{not json"), key=KEY)
    assert bad.error == "bad-json"


async def test_no_key_means_no_request(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("seoa.infrastructure.integrations.openpagerank.api_key", lambda: None)
    sess = FakeSession()
    sig = await fetch_authority("example.com", session=sess, key="")
    assert sess.calls == [] and sig.error == "no-api-key"


async def test_module_without_key_is_not_checked(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("SEOA_OPENPAGERANK_KEY", raising=False)
    inp = inputs([])
    inp.settings = type(inp.settings)(anthropic_api_key=None, openpagerank_key=None)
    res = await AuthorityModule().run(inp)
    assert res.data is None and res.findings == []
    assert [(n.check_id, n.reason_code) for n in res.not_checked] == [("authority", "no-api-key")]


async def test_module_with_key_stores_signal(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def fake(host: str, key: str) -> AuthoritySignal:
        assert host == "example.com" and key == KEY
        return AuthoritySignal(domain=host, page_rank_decimal=4.2, page_rank_integer=4, rank=99)

    inp = inputs([])
    inp.ops = SimpleNamespace(fetch_authority=fake)
    inp.settings = type(inp.settings)(anthropic_api_key=None, openpagerank_key=KEY)
    res = await AuthorityModule().run(inp)
    assert res.findings == [] and res.available == set()
    assert isinstance(res.data, AuthoritySignal) and res.data.rank == 99


async def test_module_error_becomes_a_reason(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def fake(host: str, key: str) -> AuthoritySignal:
        return AuthoritySignal(domain=host, error="rate-limited")

    inp = inputs([])
    inp.ops = SimpleNamespace(fetch_authority=fake)
    inp.settings = type(inp.settings)(anthropic_api_key=None, openpagerank_key=KEY)
    res = await AuthorityModule().run(inp)
    assert res.data is None and res.not_checked[0].reason_code == "authority-rate-limited"
