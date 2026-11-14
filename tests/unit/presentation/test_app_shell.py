"""The app shell: menu, overview, analysis tabs, chat and the connections page."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import lxml.html
import pytest

from seoa.domain import AuditStatus
from seoa.presentation.api import create_app
from tests.support.fake_service import FakeService, make_sample_record

AUD = "aud_sample0001"


@pytest.fixture
def service() -> FakeService:
    return FakeService()


@pytest.fixture
async def client(service: FakeService) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(service), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c


def _menu(root: lxml.html.HtmlElement) -> dict[str, str]:
    return {
        a.get("class", "").split()[0]: a.get("href", "")
        for a in root.xpath("//nav[@class='navlist']/a")
    }


@pytest.mark.parametrize("lang", ["tr", "en"])
async def test_overview_has_the_menu_the_score_and_links_to_every_other_page(
    client: httpx.AsyncClient, lang: str
) -> None:
    r = await client.get(f"/audits/{AUD}", params={"lang": lang})
    root = lxml.html.fromstring(r.text)
    assert r.status_code == 200 and root.get("lang") == lang
    menu = _menu(root)
    assert set(menu) == {
        "nav-overview", "nav-chat", "nav-analysis", "nav-search", "nav-rivals",
        "nav-plan", "nav-history", "nav-settings",
    }  # fmt: skip
    assert menu["nav-chat"].startswith(f"/audits/{AUD}/chat")
    assert menu["nav-analysis"].startswith(f"/audits/{AUD}/analysis")
    current = root.xpath("//nav[@class='navlist']/a[@aria-current='page']")
    assert [a.get("class").split()[0] for a in current] == ["nav-overview"]
    assert root.xpath("//nav[@class='navlist'][@aria-label]")
    assert root.xpath("//a[contains(@href, '/report')]")  # the full report stays reachable
    assert root.xpath("//a[contains(@href, '/analysis?tab=')]")  # every category opens its tab
    assert root.xpath(f"//button[@data-action-post='/v1/audits/{AUD}/rerun']")


async def test_language_switch_keeps_the_page(client: httpx.AsyncClient) -> None:
    r = await client.get(f"/audits/{AUD}/analysis", params={"lang": "tr", "tab": "content"})
    root = lxml.html.fromstring(r.text)
    link = root.xpath("//div[@class='side-foot']/a")[0].get("href")
    assert (
        link.startswith(f"/audits/{AUD}/analysis?") and "lang=en" in link and "tab=content" in link
    )


async def test_analysis_tabs_filter_the_findings_and_unknown_tabs_fall_back(
    client: httpx.AsyncClient,
) -> None:
    findings = (await client.get(f"/v1/audits/{AUD}/report", params={"lang": "en"})).json()[
        "findings"
    ]
    cats = sorted({f["category"] for f in findings})
    assert cats, "the sample audit has findings"
    r = await client.get(f"/audits/{AUD}/analysis", params={"lang": "en", "tab": cats[0]})
    root = lxml.html.fromstring(r.text)
    assert r.status_code == 200
    tabs = root.xpath("//nav[contains(@class,'tabs')]/a")
    assert len(tabs) >= len(cats)
    assert len(root.xpath("//nav[contains(@class,'tabs')]/a[@aria-current='page']")) == 1
    ids = set(root.xpath("//article[contains(@class,'f2')]/@id"))
    assert ids == {f["id"] for f in findings if f["category"] == cats[0]}
    bad = await client.get(f"/audits/{AUD}/analysis", params={"tab": "nope"})
    assert bad.status_code == 200
    page = lxml.html.fromstring(bad.text)
    assert len(page.xpath("//nav[contains(@class,'tabs')]/a[@aria-current='page']")) == 1
    too_long = await client.get(f"/audits/{AUD}/analysis", params={"tab": "x" * 41})
    assert too_long.status_code == 422


async def test_chat_page_prefills_a_question_for_a_known_finding_only(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    first = (await client.get(f"/v1/audits/{AUD}/report", params={"lang": "en"})).json()[
        "findings"
    ][0]
    r = await client.get(f"/audits/{AUD}/chat", params={"lang": "en", "finding": first["id"]})
    root = lxml.html.fromstring(r.text)
    form = root.xpath("//form[@data-chat-form]")[0]
    assert form.get("data-audit-id") == AUD
    assert root.xpath("//textarea[@id='chat-q']")[0].text_content().strip().startswith("What does")
    assert root.xpath("//label[@for='chat-q']") and root.xpath("//*[@id='chat-log'][@aria-live]")
    assert len(root.xpath("//div[@id='chat-suggest']//button[@data-q]")) == 3
    unknown = await client.get(f"/audits/{AUD}/chat", params={"lang": "en", "finding": "nope"})
    assert (
        lxml.html.fromstring(unknown.text)
        .xpath("//textarea[@id='chat-q']")[0]
        .text_content()
        .strip()
        == ""
    )
    current = lxml.html.fromstring(r.text).xpath("//nav[@class='navlist']/a[@aria-current='page']")
    assert [a.get("class").split()[0] for a in current] == ["nav-chat"]


async def test_running_audits_send_the_new_pages_to_the_progress_page(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    service.add(
        make_sample_record("gated", audit_id="aud_run").model_copy(
            update={"status": AuditStatus.RUNNING}
        )
    )
    for page in ("analysis", "chat"):
        r = await client.get(f"/audits/aud_run/{page}", params={"lang": "en"})
        assert r.status_code == 303 and r.headers["location"] == "/audits/aud_run?lang=en"


@pytest.mark.parametrize("page", ["", "/analysis", "/chat"])
async def test_unknown_audits_are_404_on_every_page(client: httpx.AsyncClient, page: str) -> None:
    assert (await client.get(f"/audits/nope{page}")).status_code == 404


async def test_settings_shows_which_connections_are_ready_and_never_the_keys(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "AIzaSyTHIS-MUST-NOT-APPEAR-0123456789"
    monkeypatch.setenv("SEOA_GOOGLE_API_KEY", secret)
    monkeypatch.delenv("SEOA_OPENPAGERANK_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-MUST-NOT-APPEAR")
    r = await client.get("/settings", params={"lang": "en"})
    root = lxml.html.fromstring(r.text)
    assert r.status_code == 200 and secret not in r.text and "MUST-NOT-APPEAR" not in r.text
    names = [n.text_content().strip() for n in root.xpath("//div[@class='cname']")]
    assert any("Google API key" in n and "Ready" in n for n in names)
    assert any("OpenPageRank" in n and "Missing" in n for n in names)
    assert any("AI key" in n and "Ready" in n for n in names)
    assert (
        "keywordseverywhere.com/account/openpagerank" in r.text
    )  # says how to get the missing key
    assert not root.xpath(
        "//nav[@class='navlist']/a[contains(@class,'nav-chat')]"
    )  # no audit picked
    assert [
        a.get("class").split()[0]
        for a in root.xpath("//nav[@class='navlist']/a[@aria-current='page']")
    ] == ["nav-settings"]


async def test_settings_keeps_the_audit_menu_when_opened_from_an_audit(
    client: httpx.AsyncClient,
) -> None:
    r = await client.get("/settings", params={"lang": "tr", "audit": AUD})
    assert "nav-chat" in _menu(lxml.html.fromstring(r.text))


async def test_xss_in_findings_is_escaped_on_the_new_pages(service: FakeService) -> None:
    service.add(make_sample_record("gated", audit_id="aud_xss", xss=True))
    transport = httpx.ASGITransport(app=create_app(service), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        report = (await c.get("/v1/audits/aud_xss/report", params={"lang": "en"})).json()
        cats = sorted({f["category"] for f in report["findings"]})
        urls = [
            "/audits/aud_xss",
            "/audits/aud_xss/chat",
            *[f"/audits/aud_xss/analysis?tab={x}" for x in cats],
        ]
        for url in urls:
            r = await c.get(url, params={"lang": "en"})
            assert r.status_code == 200 and "<script>alert" not in r.text
            root = lxml.html.fromstring(r.text)
            assert not [s for s in root.iter("script") if not s.get("src")] and not root.xpath(
                "//img"
            )


# ------------------------------------------------------------------ section pages


@pytest.mark.parametrize(
    ("page", "has", "hasnt"),
    [
        ("search", {"sec-gsc", "sec-rankings", "sec-indexability", "sec-visibility"}, {"sec-links", "sec-history"}),
        ("rivals", {"sec-competitors", "sec-authority", "sec-local"}, {"sec-gsc", "sec-history"}),
        ("history", {"sec-history"}, {"sec-competitors", "sec-gsc"}),
    ],
)  # fmt: skip
async def test_section_pages_show_only_their_own_sections(
    client: httpx.AsyncClient, page: str, has: set[str], hasnt: set[str]
) -> None:
    r = await client.get(f"/audits/{AUD}/{page}", params={"lang": "en"})
    root = lxml.html.fromstring(r.text)
    assert r.status_code == 200
    ids = set(root.xpath("//section/@id"))
    assert has <= ids and not (hasnt & ids)
    current = root.xpath("//nav[@class='navlist']/a[@aria-current='page']")
    assert [a.get("class").split()[0] for a in current] == [f"nav-{page}"]


async def test_plan_page_lists_the_phases_and_links_findings_to_their_tab(
    client: httpx.AsyncClient,
) -> None:
    r = await client.get(f"/audits/{AUD}/plan", params={"lang": "en"})
    root = lxml.html.fromstring(r.text)
    assert r.status_code == 200 and len(root.xpath("//section[contains(@class,'phase2')]")) == 4
    assert root.xpath("//section[contains(@class,'phase2')]//a[contains(@href, '/analysis?tab=')]")
    assert [
        a.get("class").split()[0]
        for a in root.xpath("//nav[@class='navlist']/a[@aria-current='page']")
    ] == ["nav-plan"]


@pytest.mark.parametrize("page", ["search", "rivals", "history", "plan"])
async def test_section_pages_404_for_unknown_and_redirect_for_running_audits(
    client: httpx.AsyncClient, service: FakeService, page: str
) -> None:
    assert (await client.get(f"/audits/nope/{page}")).status_code == 404
    service.add(
        make_sample_record("gated", audit_id="aud_run2").model_copy(
            update={"status": AuditStatus.RUNNING}
        )
    )
    r = await client.get(f"/audits/aud_run2/{page}", params={"lang": "en"})
    assert r.status_code == 303 and r.headers["location"] == "/audits/aud_run2?lang=en"


async def test_analysis_tabs_show_the_report_sections_that_belong_to_them(
    client: httpx.AsyncClient,
) -> None:
    def ids(html: str) -> set[str]:
        return set(lxml.html.fromstring(html).xpath("//section/@id"))

    tech = ids((await client.get(f"/audits/{AUD}/analysis", params={"tab": "technical"})).text)
    perf = ids((await client.get(f"/audits/{AUD}/analysis", params={"tab": "performance"})).text)
    assert {"sec-setup", "sec-techstack"} <= tech and "sec-performance" not in tech
    assert {"sec-performance", "sec-field"} <= perf and "sec-setup" not in perf


async def test_the_full_report_still_has_every_section(client: httpx.AsyncClient) -> None:
    ids = set(
        lxml.html.fromstring((await client.get(f"/audits/{AUD}/report")).text).xpath(
            "//section/@id"
        )
    )
    assert {
        "sec-links",
        "sec-gsc",
        "sec-history",
        "sec-competitors",
        "sec-readability",
        "sec-agentic",
    } <= ids


# ------------------------------------------------------------------ chat history


async def test_chat_page_shows_saved_questions_with_sources_and_escapes_them(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    first = (await client.get(f"/v1/audits/{AUD}/report", params={"lang": "tr"})).json()[
        "findings"
    ][0]
    service.qa[AUD] = [
        {
            "question": "Neden <b>böyle</b>?",
            "answer": {
                "answer": "Çünkü <script>x</script>.",
                "citations": [
                    {"finding_id": first["id"]},
                    {"finding_id": first["id"]},
                    {"finding_id": "fnd_unknown"},
                    {"score_ref": "overall"},
                ],
            },
        },
        {"question": "Peki?", "answer": {"answer": "x", "out_of_scope": True, "citations": []}},
    ]
    r = await client.get(f"/audits/{AUD}/chat", params={"lang": "tr"})
    root = lxml.html.fromstring(r.text)
    assert [d.text_content() for d in root.xpath("//div[@class='msg-u']")] == [
        "Neden <b>böyle</b>?",
        "Peki?",
    ]
    assert "<b>böyle</b>" not in r.text and not [s for s in root.iter("script") if not s.get("src")]
    chips = root.xpath("//div[@class='src']/a")
    # a known finding reads "Analiz › <category>" and links to its tab (twice cited, shown once)
    known = [a for a in chips if a.text_content().startswith("Analiz › ")]
    assert len(known) == 1 and f"/analysis?tab={first['category']}" in known[0].get("href")
    assert root.xpath("//div[@class='src']/a[contains(@href, '/report?lang=tr#fnd_unknown')]")
    assert root.xpath("//div[@class='src']/code[text()='overall']")
    assert root.xpath("//*[@id='chat-suggest'][@hidden]") and not root.xpath(
        "//*[@id='chat-empty']"
    )
    fresh = lxml.html.fromstring(
        (await client.get(f"/audits/{AUD}/chat", params={"new": "1"})).text
    )
    assert not fresh.xpath("//div[@class='msg-u']") and fresh.xpath("//*[@id='chat-empty']")


# ------------------------------------------------------------------ "Test et"


@pytest.mark.parametrize(
    ("name", "error", "ok", "code"),
    [
        ("gkey", None, True, "ok"),
        ("gkey", "no-data", True, "ok"),
        ("gkey", "http-403", False, "rejected.gkey"),
        ("gkey", "rate-limited", False, "rate-limited"),
        ("opr", "unauthorized", False, "rejected.opr"),
        ("opr", "unreachable", False, "unreachable"),
        ("opr", "no-api-key", False, "missing"),
        ("opr", "bad-json", False, "other"),
    ],
)  # fmt: skip
async def test_integration_test_reports_what_the_provider_said(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    error: str | None,
    ok: bool,
    code: str,
) -> None:
    from seoa.infrastructure.integrations import crux, openpagerank

    async def fake_crux(*_a: object, **_k: object) -> crux.FieldData:
        return crux.FieldData(error=error)

    async def fake_opr(*_a: object, **_k: object) -> openpagerank.AuthoritySignal:
        return openpagerank.AuthoritySignal(error=error)

    monkeypatch.setattr(crux, "fetch_crux", fake_crux)
    monkeypatch.setattr(openpagerank, "fetch_authority", fake_opr)
    monkeypatch.setenv("SEOA_OPENPAGERANK_KEY", "opr-secret-value")
    r = await client.post(f"/v1/integrations/{name}/test", params={"lang": "en"})
    body = r.json()
    assert r.status_code == 200 and body["ok"] is ok and body["code"] == code and body["message"]
    assert "secret" not in r.text


async def test_integration_test_rejects_unknown_names(client: httpx.AsyncClient) -> None:
    assert (await client.post("/v1/integrations/nope/test")).status_code == 422


async def test_settings_offers_a_test_button_only_for_keys_that_are_set(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEOA_GOOGLE_API_KEY", "AIzaX")
    monkeypatch.delenv("SEOA_OPENPAGERANK_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    root = lxml.html.fromstring((await client.get("/settings", params={"lang": "en"})).text)
    assert [b.get("data-test") for b in root.xpath("//button[@data-test]")] == ["gkey"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-shown")
    both = lxml.html.fromstring((await client.get("/settings", params={"lang": "en"})).text)
    assert [b.get("data-test") for b in both.xpath("//button[@data-test]")] == ["gkey", "ai"]
    assert "one very small paid call" in lxml.html.tostring(both, encoding="unicode")


@pytest.mark.parametrize(
    ("outcome", "ok", "code"),
    [
        ("ok", True, "ok"),
        ("rejected", False, "rejected.ai"),
        ("rate-limited", False, "rate-limited"),
        ("unreachable", False, "unreachable"),
        ("budget", False, "budget"),
        ("missing", False, "missing"),
    ],
)
async def test_ai_key_test_reports_the_outcome_of_one_small_call(
    client: httpx.AsyncClient, service: FakeService, outcome: str, ok: bool, code: str
) -> None:
    service.llm_test = outcome
    body = (await client.post("/v1/integrations/ai/test", params={"lang": "tr"})).json()
    assert body["ok"] is ok and body["code"] == code and body["message"]
    assert ("test_llm", ()) in service.calls


# ------------------------------------------------------------------ keyword suggestions


async def test_keyword_suggestions_come_from_the_site_s_own_search_console_queries(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    service.suggestions = {
        "status": "ok",
        "keywords": [{"query": "last check", "impressions": 12, "clicks": 1}],
    }
    r = await client.get(
        "/ui/suggest-keywords", params={"url": "https://www.example.com/x", "lang": "en"}
    )
    body = r.json()
    assert body["status"] == "ok" and body["keywords"][0]["query"] == "last check"
    assert body["message"] and r.headers["cache-control"] == "no-store"
    assert ("suggest_keywords", ("https://www.example.com/x",)) in service.calls


@pytest.mark.parametrize(
    ("state", "snippet"),
    [
        ("not-connected", "Not connected"),
        ("property-not-found", "not found"),
        ("empty", "no search data"),
    ],
)
async def test_keyword_suggestions_explain_why_there_are_none(
    client: httpx.AsyncClient, service: FakeService, state: str, snippet: str
) -> None:
    service.suggestions = {"status": state, "keywords": []}
    body = (
        await client.get("/ui/suggest-keywords", params={"url": "example.com", "lang": "en"})
    ).json()
    assert body["keywords"] == [] and snippet.lower() in body["message"].lower()


async def test_keyword_suggestions_reject_a_missing_or_bad_address(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    for bad in ("", "   "):
        body = (await client.get("/ui/suggest-keywords", params={"url": bad, "lang": "en"})).json()
        assert body["status"] == "bad-url" and body["keywords"] == []
    assert not [c for c in service.calls if c[0] == "suggest_keywords"]


async def test_home_form_has_the_suggest_button(client: httpx.AsyncClient) -> None:
    root = lxml.html.fromstring((await client.get("/", params={"lang": "tr"})).text)
    assert root.xpath("//button[@id='suggest-btn']") and root.xpath("//*[@id='suggest-chips']")


# ------------------------------------------------------------------ the full report in the new look


async def test_full_report_uses_the_new_theme_and_links_back_to_the_app_pages(
    client: httpx.AsyncClient,
) -> None:
    r = await client.get(f"/audits/{AUD}/report", params={"lang": "en"})
    root = lxml.html.fromstring(r.text)
    assert "--ap-accent" in r.text  # the shared tokens are part of the page
    hrefs = {a.get("href") for a in root.xpath("//div[@class='actions']/a")}
    assert {
        f"/audits/{AUD}?lang=en",
        f"/audits/{AUD}/analysis?lang=en",
        f"/audits/{AUD}/chat?lang=en",
    } <= hrefs
