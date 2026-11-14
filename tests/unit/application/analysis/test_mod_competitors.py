"""mod_competitors: light comparison of the entry page of up to three competitors."""

from __future__ import annotations

from seoa.application.analysis import plugin
from seoa.application.analysis.modules.competitors import CompetitorComparison, CompetitorsModule
from seoa.domain.parsing.html import parse_html
from tests.support.modules import HOST, Scripted, inputs

GOOD = """<!doctype html><html lang="en"><head><title>Competitor home page title for tests</title>
<meta name="description" content="A description of a reasonable length that describes this page well enough.">
<link rel="canonical" href="https://rival.example/"><meta name="generator" content="WordPress 6.4">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Rival","url":"https://rival.example/"}</script>
</head><body><h1>Rival</h1><p>{text}</p><img src="a.png" alt="a"><img src="b.png">
<a href="/about">About</a><a href="https://other.example/">Other</a></body></html>""".replace(
    "{text}", "This is a sentence about our products. " * 30
)
MINE = "<!doctype html><html lang='en'><head><title>Mine</title></head><body><h1>Mine</h1><p>Short.</p></body></html>"


def _inp(competitors: list[object], table: dict | None = None):  # type: ignore[no-untyped-def]
    fetcher = Scripted(table or {})
    inp = inputs([], fetcher, entry_html=MINE)
    inp.options = {"competitors": competitors}
    return inp, fetcher


async def test_row_per_competitor_with_metrics_and_you_row() -> None:
    inp, fetcher = _inp(
        ["https://rival.example/"], {"https://rival.example/": (200, {"Server": "nginx"}, GOOD)}
    )
    res = await CompetitorsModule().run(inp)
    data = CompetitorComparison.model_validate(res.data.model_dump())  # type: ignore[union-attr]
    assert res.findings == [] and res.available == set()  # competitors never affect the score
    assert fetcher.requested == ["https://rival.example/"]
    (row,) = data.rows
    assert row.host == "rival.example" and row.status == 200 and row.score is not None
    assert row.h1_count == 1 and row.images == 2 and row.images_alt_pct == 50.0
    assert row.canonical == "self" and row.noindex is False
    assert row.internal_links == 1 and row.external_links == 1
    assert "Organization" in row.schema_types and row.words and row.words > 100
    assert any("WordPress" in n for n in row.tech)
    assert data.you is not None and data.you.is_you and data.you.h1_count == 1
    assert data.you.score is not None


async def test_scores_are_computed_the_same_way_for_both_sides() -> None:
    inp, _ = _inp(["https://rival.example/"], {"https://rival.example/": (200, {}, MINE)})
    res = await CompetitorsModule().run(inp)
    data = CompetitorComparison.model_validate(res.data.model_dump())  # type: ignore[union-attr]
    assert data.you is not None and data.rows[0].score == data.you.score


async def test_no_competitors_is_not_checked_not_an_error() -> None:
    res = await CompetitorsModule().run(_inp([])[0])
    assert res.data is None
    assert [(n.check_id, n.reason_code) for n in res.not_checked] == [
        ("competitors", "no-competitors")
    ]


async def test_at_most_three_requests_and_skips_are_recorded() -> None:
    urls = [
        "https://a.example/",
        "https://a.example/other",  # same host: duplicate
        f"{HOST}/page",  # the audited site itself
        "javascript:alert(1)",
        "https://b.example/",
        "https://c.example/",
        "https://d.example/",  # over the limit
    ]
    table = {u: (200, {}, MINE) for u in urls}
    inp, fetcher = _inp(urls, table)
    res = await CompetitorsModule().run(inp)
    data = CompetitorComparison.model_validate(res.data.model_dump())  # type: ignore[union-attr]
    assert len(fetcher.requested) == 3
    assert [r.host for r in data.rows] == ["a.example", "b.example", "c.example"]
    reasons = {x.reason for x in data.skipped}
    assert reasons == {"duplicate", "same-site", "invalid-url", "over-limit"}


async def test_bare_domain_gets_https() -> None:
    inp, fetcher = _inp(["rival.example"], {"https://rival.example": (200, {}, MINE)})
    await CompetitorsModule().run(inp)
    assert fetcher.requested == ["https://rival.example"]


async def test_error_status_and_rejected_target_keep_a_row_without_numbers() -> None:
    from seoa.domain import FetchResult

    class Rejecting(Scripted):
        async def fetch(self, url: str, **kw: object) -> FetchResult:  # type: ignore[override]
            self.requested.append(url)
            if "private" in url:
                return FetchResult(url=url, final_url=url, error="target-rejected")
            return await super().fetch(url)

    fetcher = Rejecting({"https://gone.example/": (404, {}, "")})
    inp = inputs([], fetcher, entry_html=MINE)
    inp.options = {"competitors": ["https://private.example/", "https://gone.example/"]}
    res = await CompetitorsModule().run(inp)
    data = CompetitorComparison.model_validate(res.data.model_dump())  # type: ignore[union-attr]
    rejected, gone = data.rows
    assert rejected.error == "target-rejected" and rejected.score is None
    assert gone.status == 404 and gone.score is None and gone.title_len is None


async def test_a_fetcher_that_raises_does_not_break_the_module() -> None:
    class Boom(Scripted):
        async def fetch(self, url: str, **kw: object):  # type: ignore[no-untyped-def,override]
            raise RuntimeError("secret detail")

    inp = inputs([], Boom(), entry_html=MINE)
    inp.options = {"competitors": ["https://rival.example/"]}
    res = await CompetitorsModule().run(inp)
    assert res.data.rows[0].error == "unreachable"  # type: ignore[union-attr]
    assert "secret" not in res.data.model_dump_json()  # type: ignore[union-attr]


async def test_non_html_response_is_marked() -> None:
    inp, _ = _inp(["https://rival.example/"], {"https://rival.example/": (200, {}, "")})
    res = await CompetitorsModule().run(inp)
    assert res.data.rows[0].error == "not-html"  # type: ignore[union-attr]


async def test_noindex_and_other_canonical_are_detected() -> None:
    page = (
        "<html><head><title>T</title><meta name='robots' content='noindex'>"
        "<link rel='canonical' href='https://elsewhere.example/'></head><body><h1>x</h1></body></html>"
    )
    inp, _ = _inp(["https://rival.example/"], {"https://rival.example/": (200, {}, page)})
    row = (await CompetitorsModule().run(inp)).data.rows[0]  # type: ignore[union-attr]
    assert row.noindex is True and row.canonical == "other"
    assert parse_html(page, "https://rival.example/").title == "T"


def test_module_is_registered() -> None:
    assert any(m.name == "competitors" for m in plugin.modules())
