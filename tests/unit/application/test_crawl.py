from __future__ import annotations

from seoa.application.crawl.sampling import Candidate, select_sample
from seoa.domain.urls import (
    in_scope,
    is_crawlable_page,
    is_low_value,
    normalize_url,
    template_key,
    url_key,
)


def test_normalize() -> None:
    assert (
        normalize_url("HTTPS://Example.COM:443/a//b/?utm_source=x&q=1#frag")
        == "https://example.com/a/b/?q=1"
    )
    assert normalize_url("/x", base="https://e.com/y/") == "https://e.com/x"
    for bad in ("javascript:void(0)", "mailto:a@b.c", "tel:1", "#top", "", "ftp://x.com/"):
        assert normalize_url(bad) is None


def test_url_key_collapses_www_scheme_and_trailing_slash() -> None:
    assert url_key("http://www.e.com/a/") == url_key("https://e.com/a")


def test_scope_and_assets() -> None:
    assert in_scope("https://www.e.com/x", "e.com") and not in_scope(
        "https://blog.e.com/x", "e.com"
    )
    assert not is_crawlable_page("https://e.com/a.pdf") and is_crawlable_page("https://e.com/a")


def test_template_keys() -> None:
    assert template_key("https://e.com/") == "/"
    assert template_key("https://e.com/blog/my-first-post") == "/blog/*"
    assert template_key("https://e.com/about") == "/about"
    assert template_key("https://e.com/my-long-slug-page") == "/*"
    assert template_key("https://e.com/urun/123?color=red&size=m") == "/urun/*?color,size"
    assert is_low_value("https://e.com/blog/page/2") and not is_low_value("https://e.com/blog/x")


def _cands() -> list[Candidate]:
    c = [
        Candidate(
            f"https://e.com/blog/post-{i}-x", lastmod=f"2026-01-{i % 28 + 1:02d}", in_sitemap=True
        )
        for i in range(300)
    ]
    c += [Candidate(f"https://e.com/urun/{i}", in_sitemap=True) for i in range(100)]
    c += [
        Candidate("https://e.com/about"),
        Candidate("https://e.com/contact"),
        Candidate("https://e.com/"),
    ]
    return c


def test_sample_is_deterministic_and_respects_n() -> None:
    a, _ = select_sample(_cands(), n=25, seed=7, mandatory=["https://e.com/"])
    b, _ = select_sample(_cands(), n=25, seed=7, mandatory=["https://e.com/"])
    assert (
        [s.url for s in a] == [s.url for s in b] and len(a) == 25 and a[0].url == "https://e.com/"
    )


def test_core_part_is_seed_independent_exploration_is_not() -> None:
    a, _ = select_sample(_cands(), n=25, seed=1, mandatory=["https://e.com/"])
    b, _ = select_sample(_cands(), n=25, seed=2, mandatory=["https://e.com/"])
    core = lambda s: {x.url for x in s if x.sample_kind == "core"}  # noqa: E731
    expl = lambda s: {x.url for x in s if x.sample_kind == "exploration"}  # noqa: E731
    assert core(a) == core(b) and expl(a) != expl(b)


def test_no_single_template_dominates_when_other_templates_can_fill_the_sample() -> None:
    c = _cands()
    c += [Candidate(f"https://e.com/news/story-{i}-a", in_sitemap=True) for i in range(200)]
    c += [Candidate(f"https://e.com/docs/guide-{i}-b", in_sitemap=True) for i in range(200)]
    s, stats = select_sample(c, n=30, seed=3, mandatory=["https://e.com/"])
    per: dict[str, int] = {}
    for x in s:
        per[x.template_key] = per.get(x.template_key, 0) + 1
    assert len(s) == 30 and max(per.values()) <= 11  # <= n/3 + the fixed representative
    assert {"/blog/*", "/urun/*", "/news/*", "/docs/*", "/about", "/contact"} <= set(per)
    assert stats["/blog/*"]["discovered"] == 300


def test_cap_relaxes_only_when_nothing_else_can_fill_the_sample() -> None:
    s, _ = select_sample(_cands(), n=30, seed=3, mandatory=["https://e.com/"])
    assert len(s) == 30  # two big templates + three singletons: the cap must give way to reach n


def test_small_sites_are_sampled_completely() -> None:
    cands = [Candidate(f"https://e.com/p{i}") for i in range(5)]
    s, _ = select_sample(cands, n=25, seed=1)
    assert len(s) == 5


def test_duplicates_are_collapsed() -> None:
    cands = [Candidate("https://e.com/a"), Candidate("http://www.e.com/a/")]
    s, _ = select_sample(cands, n=10, seed=1)
    assert len(s) == 1


def test_cdn_cgi_paths_are_infrastructure_not_pages() -> None:
    from seoa.domain.urls import is_infrastructure_path

    assert is_infrastructure_path("https://e.com/cdn-cgi/l/email-protection")
    assert not is_crawlable_page("https://e.com/cdn-cgi/l/email-protection")
    assert not is_infrastructure_path("https://e.com/blog/cdn-cgi")
