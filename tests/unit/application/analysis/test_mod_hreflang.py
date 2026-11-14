"""Hreflang module: codes, return links, targets, canonical conflicts, hostile input."""

from __future__ import annotations

import pytest

from seoa.application.analysis.modules import hreflang as H
from seoa.application.analysis.plugin import modules
from seoa.domain.rules.registry import MESSAGES, RULES
from tests.support.modules import HOST, Scripted, inputs, page


def doc(lang: str, alts: list[tuple[str, str]], extra: str = "") -> str:
    links = "".join(f'<link rel="alternate" hreflang="{h}" href="{u}">' for h, u in alts)
    return f'<html lang="{lang}"><head><title>t</title>{extra}{links}</head><body><main>x</main></body></html>'


EN, TR = f"{HOST}/en/", f"{HOST}/tr/"
FULL = [("en", EN), ("tr", TR), ("x-default", EN)]


async def run(pages, fetcher=None):  # type: ignore[no-untyped-def]
    res = await H.HreflangModule().run(inputs(pages, fetcher))
    return res, [f.id for f in res.findings]


def test_registered_with_messages_and_unique_ids() -> None:
    from seoa.application.rules_loader import load_all_rules

    load_all_rules()
    assert "hreflang" in {m.name for m in modules()}
    for rid in H.HREFLANG_RULE_IDS:
        assert rid in RULES
        d = RULES[rid]
        for key in (d.message_key, d.recommendation_key, d.failure_check_key):
            assert {"en", "tr"} <= set(MESSAGES[key])
    assert "hreflang-missing-self" in RULES  # the existing page check is not duplicated
    assert "hreflang-missing-self" not in H.HREFLANG_RULE_IDS


@pytest.mark.parametrize(
    ("code", "ok"),
    [
        ("en", True),
        ("en-GB", True),
        ("en-gb", True),
        ("pt-BR", True),
        ("zh-Hant", True),
        ("zh-Hans-US", True),
        ("x-default", True),
        ("eng", False),
        ("jp", False),
        ("en-uk", False),
        ("GB", False),
        ("be-", False),
        ("", False),
        ("en-US-extra-more", False),
    ],
)
def test_code_validation(code: str, ok: bool) -> None:
    assert H.valid_hreflang_code(code) is ok


async def test_clean_reciprocal_set_has_no_findings_and_no_network() -> None:
    f = Scripted()
    res, ids = await run(
        [page("/en/", doc("en", FULL)), page("/tr/", doc("tr", FULL))],
        f,
    )
    assert ids == []
    assert f.requested == []
    assert res.data.applicable and res.data.languages == ["en", "tr"] and res.data.has_x_default


async def test_one_way_link_is_no_return_link_high() -> None:
    res, ids = await run(
        [
            page("/en/", doc("en", FULL)),
            page("/tr/", doc("tr", [("tr", TR)])),  # tr never points back to en
        ]
    )
    assert "hreflang-no-return-link" in ids
    f = next(x for x in res.findings if x.id == "hreflang-no-return-link")
    assert f.url == EN and f.severity.value == "High"


async def test_invalid_codes_and_duplicate_language() -> None:
    alts = [("eng", EN), ("tr", TR), ("tr", f"{HOST}/tr2/")]
    res, ids = await run([page("/en/", doc("en", alts))], Scripted())
    assert "hreflang-invalid-code" in ids
    assert "hreflang-duplicate-language" in ids


async def test_target_outside_sample_is_probed_and_judged() -> None:
    table = {
        TR: (200, {}, doc("tr", FULL)),
        f"{HOST}/de/": (404, {}, ""),
        f"{HOST}/fr/": (
            200,
            {},
            doc("fr", [("fr", f"{HOST}/fr/")], '<meta name="robots" content="noindex">'),
        ),
        f"{HOST}/es/": (
            200,
            {},
            doc("es", FULL, f'<link rel="canonical" href="{HOST}/es-elsewhere/">'),
        ),
    }
    f = Scripted(table)
    alts = FULL + [("de", f"{HOST}/de/"), ("fr", f"{HOST}/fr/"), ("es", f"{HOST}/es/")]
    res, ids = await run([page("/en/", doc("en", alts))], f)
    assert "hreflang-target-not-200" in ids
    assert "hreflang-target-noindex" in ids
    assert "hreflang-canonical-conflict" in ids
    assert f"{HOST}/de/" in res.data.probed
    # fr does not link back to en -> also a return-link error
    assert "hreflang-no-return-link" in ids


async def test_redirecting_target_is_not_200() -> None:
    f = Scripted({TR: (200, {}, f"redirect:{HOST}/tr-final/")})
    _res, ids = await run([page("/en/", doc("en", FULL))], f)
    assert "hreflang-target-not-200" in ids


async def test_probe_limit_is_not_checked_not_a_finding() -> None:
    alts = [("en", EN)] + [
        (f"{c}", f"{HOST}/{c}/") for c in "de fr es it nl pl pt ru sv da".split()
    ]
    table = {
        u: (200, {}, doc(c, alts))
        for c, u in [(c, f"{HOST}/{c}/") for c in "de fr es it nl pl pt ru sv da".split()]
    }
    f = Scripted(table)
    res, ids = await run([page("/en/", doc("en", alts))], f)
    assert len(f.requested) == H.MAX_PROBES
    assert res.data.unchecked == 10 - H.MAX_PROBES
    assert any(n.reason_code == "probe-limit" for n in res.not_checked)


async def test_canonical_elsewhere_on_the_page_itself() -> None:
    other = f'<link rel="canonical" href="{HOST}/somewhere-else/">'
    _res, ids = await run([page("/en/", doc("en", FULL, other)), page("/tr/", doc("tr", FULL))])
    assert "hreflang-canonical-conflict" in ids


async def test_x_default_recommendation_and_lang_attr_mismatch() -> None:
    alts = [("en", EN), ("tr", TR)]
    res, ids = await run(
        [page("/en/", doc("de", alts)), page("/tr/", doc("tr", alts))],
    )
    assert "hreflang-no-x-default" in ids
    assert "hreflang-lang-attr-mismatch" in ids
    f = next(x for x in res.findings if x.id == "hreflang-no-x-default")
    assert f.heuristic and f.severity.value == "Low"


async def test_http_link_header_is_supported() -> None:
    hdr = f'<{EN}>; rel="alternate"; hreflang="en", <{TR}>; rel="alternate"; hreflang="tr"'
    p = page("/en/", "<html lang='en'><body>x</body></html>", headers={"Link": hdr})
    res, _ids = await run([p, page("/tr/", doc("tr", [("en", EN), ("tr", TR)]))])
    assert res.data.applicable
    assert {e.source for r in res.data.pages for e in r.entries} == {"header", "html"}


def test_link_header_parser_ignores_non_hreflang_and_garbage() -> None:
    assert H.link_header_hreflang('<https://a/>; rel="canonical"', HOST) == []
    assert H.link_header_hreflang("<<<>>>;;;; hreflang=", HOST) == []
    assert H.link_header_hreflang("x" * 100000, HOST) == []


async def test_no_hreflang_single_language_is_not_applicable() -> None:
    res, ids = await run([page("/", "<html lang='en'><body>hi</body></html>")])
    assert ids == []
    assert res.data.applicable is False
    assert [(n.check_id, n.reason_code) for n in res.not_checked] == [
        ("hreflang", "not-applicable")
    ]
    assert "single-language-site" in res.data.notes


async def test_multilingual_signals_without_hreflang_are_noted_not_flagged() -> None:
    html = (
        "<html lang='en'><body><nav><a href='/tr/'>TR</a><a href='/en/'>EN</a></nav></body></html>"
    )
    res, ids = await run([page("/", html), page("/tr/", "<html lang='tr'><body>x</body></html>")])
    assert ids == []
    assert res.data.multilingual_signals
    assert "multilingual-without-hreflang" in res.data.notes


async def test_hostile_input_is_contained() -> None:
    evil = [("en" * 5000, "javascript:alert(1)"), ("<script>", "http://[::1"), ("tr", "not a url")]
    many = [(f"en-{i}", f"{HOST}/{i}") for i in range(500)]
    res, _ids = await run([page("/en/", doc("en", evil + many))], Scripted())
    assert len(res.data.pages[0].entries) <= H.MAX_ENTRIES_PER_PAGE
    assert all(len(e.lang) <= 20 for e in res.data.pages[0].entries)


async def test_failed_pages_are_ignored() -> None:
    p = page("/en/", doc("en", FULL), status=500)
    res, ids = await run([p])
    assert ids == [] and res.data.applicable is False
