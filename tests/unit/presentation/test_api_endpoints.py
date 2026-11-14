from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest

from seoa.application.reporting.schema import AuditReport, Quality, QualityCheck
from seoa.domain import AuditStatus, Category, Severity
from seoa.domain.rules import registry
from seoa.presentation.api import create_app
from seoa.presentation.api import support as routes_mod
from tests.support.fake_service import FakeService, make_sample_record

AUD = "aud_sample0001"


@pytest.fixture
def service() -> FakeService:
    return FakeService()


@pytest.fixture
async def client(service: FakeService) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(service)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c


def _problem(r: httpx.Response) -> dict[str, object]:
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert {"type", "title", "status", "detail", "instance", "code", "trace_id"} <= body.keys()
    assert body["status"] == r.status_code
    return body  # type: ignore[no-any-return]


# ------------------------------------------------------------------ create / list / get


async def test_create_audit_returns_202_location_and_links(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    r = await client.post(
        "/v1/audits",
        json={"url": "Example.org/path#frag", "mode": "page", "max_pages": 10, "enable_llm": False},
    )
    assert r.status_code == 202
    body = r.json()
    assert r.headers["location"] == f"/v1/audits/{body['id']}" and body["status"] == "queued"
    assert service.calls[-1] == ("create_audit", ("https://Example.org/path", "page", 10, False))


async def test_create_defaults_to_site_mode_and_adds_https(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    r = await client.post("/v1/audits", json={"url": "  example.net  "})
    assert r.status_code == 202
    assert service.calls[-1][1][:2] == ("https://example.net", "site")


@pytest.mark.parametrize(
    "payload",
    [
        {"url": ""},
        {"url": "ftp://example.com"},
        {"url": "javascript:alert(1)"},
        {"url": "https://user:pw@example.com"},
        {"url": "https://exa mple.com"},
        {"url": "https://example.com:notaport/"},
        {"url": "x" * 2049},
        {"url": "example.com", "mode": "everything"},
        {"url": "example.com", "max_pages": 0},
        {"url": "example.com", "max_pages": 201},
        {"mode": "site"},
        {},
    ],
)
async def test_create_validation_errors_are_problem_json(
    client: httpx.AsyncClient, payload: dict[str, object]
) -> None:
    r = await client.post("/v1/audits", json=payload)
    assert r.status_code == 422
    body = _problem(r)
    assert body["code"] == "validation-error" and body["errors"]


async def test_create_rejects_malformed_json(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/v1/audits", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 422 and _problem(r)["code"] == "validation-error"


async def test_duplicate_active_audit_is_409_with_link(client: httpx.AsyncClient) -> None:
    first = await client.post("/v1/audits", json={"url": "dup.example", "mode": "site"})
    assert first.status_code == 202
    second = await client.post("/v1/audits", json={"url": "dup.example", "mode": "site"})
    body = _problem(second)
    assert second.status_code == 409 and body["code"] == "audit-in-progress" and "existing" in body
    other_mode = await client.post("/v1/audits", json={"url": "dup.example", "mode": "page"})
    assert other_mode.status_code == 202  # same site, different mode is allowed


async def test_idempotency_key_replays_and_detects_reuse(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    h = {"Idempotency-Key": "k1"}
    a = await client.post("/v1/audits", json={"url": "idem.example"}, headers=h)
    b = await client.post("/v1/audits", json={"url": "idem.example"}, headers=h)
    assert a.status_code == b.status_code == 202 and a.json()["id"] == b.json()["id"]
    assert len([c for c in service.calls if c[0] == "create_audit"]) == 1
    c = await client.post("/v1/audits", json={"url": "other.example"}, headers=h)
    assert c.status_code == 422 and _problem(c)["code"] == "idempotency-key-reuse"


async def test_list_and_get_audit(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/audits", params={"limit": 5})
    body = r.json()
    assert r.status_code == 200 and body["has_more"] is False and body["data"][0]["id"] == AUD
    g = await client.get(f"/v1/audits/{AUD}")
    j = g.json()
    assert g.status_code == 200 and j["status"] == "completed" and j["overall"] == 40.0
    assert j["partial_available"] is True and j["links"]["report"].endswith("/report")
    assert (await client.get("/v1/audits", params={"limit": 0})).status_code == 422


async def test_unknown_audit_is_404_everywhere(client: httpx.AsyncClient) -> None:
    for method, path, body in [
        ("GET", "/v1/audits/nope", None),
        ("GET", "/v1/audits/nope/report", None),
        ("GET", "/v1/audits/nope/findings", None),
        ("GET", "/v1/audits/nope/pages", None),
        ("GET", "/v1/audits/nope/events", None),
        ("POST", "/v1/audits/nope/cancel", {}),
        ("POST", "/v1/audits/nope/rerun", {"modules": ["checks"]}),
        ("POST", "/v1/audits/nope/qa", {"question": "hi"}),
    ]:
        r = await client.request(method, path, json=body)
        assert r.status_code == 404 and _problem(r)["code"] == "not-found", (method, path)


# ------------------------------------------------------------------ report / findings / pages


async def test_report_json_and_html_and_language(client: httpx.AsyncClient) -> None:
    j = await client.get(f"/v1/audits/{AUD}/report", params={"lang": "en"})
    report = AuditReport.model_validate(j.json())
    assert (
        j.status_code == 200
        and report.audit.locale == "en"
        and report.scores.overall.gate is not None
    )
    assert report.quality.status in ("PASS", "WARN")
    h = await client.get(f"/v1/audits/{AUD}/report", params={"format": "html", "lang": "tr"})
    assert (
        h.status_code == 200
        and h.headers["content-type"].startswith("text/html")
        and "Skor sınırlandırıldı" in h.text
    )
    assert (
        await client.get(f"/v1/audits/{AUD}/report", params={"format": "pdf"})
    ).status_code == 422


async def test_accept_language_header_picks_the_language(client: httpx.AsyncClient) -> None:
    r = await client.get(f"/v1/audits/{AUD}/report", headers={"Accept-Language": "en-US,en;q=0.9"})
    assert r.json()["audit"]["locale"] == "en"
    r2 = await client.get(f"/v1/audits/{AUD}/report", headers={"Accept-Language": "de"})
    assert r2.json()["audit"]["locale"] == "tr"


async def test_report_of_unfinished_audit_is_409(client: httpx.AsyncClient) -> None:
    new = (await client.post("/v1/audits", json={"url": "queued.example"})).json()["id"]
    r = await client.get(f"/v1/audits/{new}/report")
    assert r.status_code == 409 and _problem(r)["code"] == "audit-not-ready"


async def test_report_of_failed_audit_is_available_without_a_score(
    client: httpx.AsyncClient,
) -> None:
    new = (await client.post("/v1/audits", json={"url": "fail.example"})).json()["id"]
    r = await client.get(f"/v1/audits/{new}/report", params={"lang": "en"})
    body = r.json()
    assert (
        r.status_code == 200
        and body["audit"]["status"] == "failed"
        and body["scores"]["overall"]["value"] is None
    )


async def test_report_quality_gate_failure_blocks_the_report(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(report: AuditReport, html: str | None = None, **_: object) -> Quality:
        return Quality(
            status="FAIL", checks=[QualityCheck(id="html.escaping", status="FAIL", detail="boom")]
        )

    monkeypatch.setattr(routes_mod, "check_report", fail)
    r = await client.get(f"/v1/audits/{AUD}/report")
    body = _problem(r)
    assert (
        r.status_code == 500
        and body["code"] == "report-invalid"
        and body["errors"][0]["field"] == "html.escaping"
    )
    ui = await client.get(f"/audits/{AUD}/report")
    assert ui.status_code == 500  # the HTML route never shows a failed report either


async def test_findings_filters_sorting_and_pagination(client: httpx.AsyncClient) -> None:
    allf = (await client.get(f"/v1/audits/{AUD}/findings", params={"limit": 200})).json()
    assert allf["total"] == len(allf["data"]) >= 10 and allf["has_more"] is False
    sev = [f["severity"] for f in allf["data"]]
    order = [s.value for s in Severity]
    assert sev == sorted(sev, key=order.index)  # severity order by default
    high = (await client.get(f"/v1/audits/{AUD}/findings", params={"severity": "High"})).json()
    assert high["data"] and {f["severity"] for f in high["data"]} == {"High"}
    cat = (
        await client.get(f"/v1/audits/{AUD}/findings", params={"category": Category.ONPAGE.value})
    ).json()
    assert {f["category"] for f in cat["data"]} == {"onpage"}
    one = (await client.get(f"/v1/audits/{AUD}/findings", params={"check_id": "noindex"})).json()
    assert [f["check_id"] for f in one["data"]] == ["noindex"]
    p1 = (await client.get(f"/v1/audits/{AUD}/findings", params={"limit": 3})).json()
    assert len(p1["data"]) == 3 and p1["has_more"] and p1["next_cursor"] == "3"
    p2 = (
        await client.get(
            f"/v1/audits/{AUD}/findings", params={"limit": 3, "cursor": p1["next_cursor"]}
        )
    ).json()
    assert {f["id"] for f in p1["data"]}.isdisjoint({f["id"] for f in p2["data"]})
    assert (
        await client.get(f"/v1/audits/{AUD}/findings", params={"cursor": "abc"})
    ).status_code == 422
    assert (
        await client.get(f"/v1/audits/{AUD}/findings", params={"severity": "Huge"})
    ).status_code == 422
    assert (
        await client.get(f"/v1/audits/{AUD}/findings", params={"sort": "priority"})
    ).status_code == 200


async def test_pages_endpoint(client: httpx.AsyncClient) -> None:
    body = (await client.get(f"/v1/audits/{AUD}/pages")).json()
    assert len(body["data"]) == 10 and {p["role"] for p in body["data"]} == {"core", "exploration"}


# ------------------------------------------------------------------ events / cancel / rerun / qa


def _parse_sse(text: str) -> list[dict[str, str]]:
    out = []
    for block in text.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if fields:
            out.append(fields)
    return out


async def test_sse_stream_has_ids_event_names_and_valid_json(client: httpx.AsyncClient) -> None:
    r = await client.get(f"/v1/audits/{AUD}/events")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-cache"
    events = [e for e in _parse_sse(r.text) if "data" in e]
    assert [e["id"] for e in events] == [str(i) for i in range(1, len(events) + 1)] and len(
        events
    ) >= 6
    assert events[0]["event"] == "stage" and events[-1]["event"] == "audit"
    assert json.loads(events[-1]["data"])["status"] == "completed"


async def test_sse_resumes_after_last_event_id(client: httpx.AsyncClient) -> None:
    full = [e for e in _parse_sse((await client.get(f"/v1/audits/{AUD}/events")).text) if "id" in e]
    part = [
        e
        for e in _parse_sse(
            (await client.get(f"/v1/audits/{AUD}/events", headers={"Last-Event-ID": "4"})).text
        )
        if "id" in e
    ]
    assert [e["id"] for e in part] == [e["id"] for e in full if int(e["id"]) > 4]
    junk = await client.get(f"/v1/audits/{AUD}/events", headers={"Last-Event-ID": "zzz"})
    assert junk.status_code == 200


async def test_cancel(client: httpx.AsyncClient) -> None:
    new = (await client.post("/v1/audits", json={"url": "cancel.example"})).json()["id"]
    r = await client.post(f"/v1/audits/{new}/cancel")
    assert r.status_code == 200 and r.json() == {"id": new, "canceled": True, "status": "canceled"}
    again = await client.post(f"/v1/audits/{new}/cancel")
    assert again.json()["canceled"] is False  # already terminal
    done = await client.post(f"/v1/audits/{AUD}/cancel")
    assert done.json()["canceled"] is False and done.json()["status"] == "completed"


async def test_rerun(client: httpx.AsyncClient, service: FakeService) -> None:
    r = await client.post(f"/v1/audits/{AUD}/rerun", json={"modules": ["checks", "advise"]})
    body = r.json()
    assert (
        r.status_code == 202
        and body["parent_audit_id"] == AUD
        and r.headers["location"].endswith(body["id"])
    )
    assert service.calls[-1] == ("rerun", (AUD, ("checks", "advise")))
    assert service.audits[body["id"]].parent_audit_id == AUD
    for bad in ({"modules": []}, {"modules": ["Checks!"]}, {"modules": ["a"] * 7}, {}):
        assert (await client.post(f"/v1/audits/{AUD}/rerun", json=bad)).status_code == 422


async def test_rerun_service_error_is_rendered_as_problem(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    from seoa.presentation.api import ApiError

    async def boom(audit_id: str, modules: list[str]) -> str:
        raise ApiError("snapshot-expired", 409, "Stored data has expired.")

    service.rerun = boom  # type: ignore[method-assign]
    r = await client.post(f"/v1/audits/{AUD}/rerun", json={"modules": ["advise"]})
    assert r.status_code == 409 and _problem(r)["code"] == "snapshot-expired"


async def test_qa(client: httpx.AsyncClient) -> None:
    r = await client.post(f"/v1/audits/{AUD}/qa", json={"question": "What should I fix first?"})
    body = r.json()
    assert (
        r.status_code == 200
        and body["citations"][0]["finding_id"] == "noindex"
        and body["out_of_scope"] is False
    )
    oos = (await client.post(f"/v1/audits/{AUD}/qa", json={"question": "xyzzy"})).json()
    assert oos["out_of_scope"] is True
    for bad in ({"question": ""}, {"question": "   "}, {"question": "q" * 501}, {}):
        assert (await client.post(f"/v1/audits/{AUD}/qa", json=bad)).status_code == 422
    new = (await client.post("/v1/audits", json={"url": "qa-queued.example"})).json()["id"]
    assert (await client.post(f"/v1/audits/{new}/qa", json={"question": "hi"})).status_code == 409


# ------------------------------------------------------------------ meta


async def test_rules_lists_the_registry(client: httpx.AsyncClient) -> None:
    from seoa.domain.rules.registry import CheckDef

    d = CheckDef("x-api-test-rule", Category.ONPAGE, Severity.LOW, heuristic=True)
    registry.register(d)
    try:
        body = (await client.get("/v1/rules")).json()
        row = next(r for r in body["data"] if r["id"] == "x-api-test-rule")
        assert (
            row["severity"] == "Low"
            and row["heuristic"] is True
            and row["message_key"] == "finding.x-api-test-rule"
        )
        assert body["count"] == len(body["data"])
    finally:
        registry.RULES.pop("x-api-test-rule", None)


async def test_spend_health_and_openapi(client: httpx.AsyncClient) -> None:
    assert (await client.get("/v1/spend")).json() == {"spent_usd": 0.0123, "cap_usd": 8.0}
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    spec = (await client.get("/v1/openapi.json")).json()
    assert "/v1/audits" in spec["paths"]
    assert (await client.get("/docs")).status_code == 404  # Swagger UI needs a CDN the CSP forbids


async def test_lifespan_starts_and_stops_the_service(service: FakeService) -> None:
    app = create_app(service)
    async with app.router.lifespan_context(app):
        assert ("start", ()) in service.calls
    assert ("stop", ()) in service.calls


async def test_status_enum_values_match_the_contract(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    for st in AuditStatus:
        rec = make_sample_record("gated", audit_id=f"aud_st_{st.value}")
        rec.status = st
        service.add(rec)
        body = (await client.get(f"/v1/audits/aud_st_{st.value}")).json()
        assert body["status"] == st.value
