"""Schema suggestions module (belge 12 A7): copy-paste JSON-LD for what a page is missing.

Adapted from the upstream project ``skills/seo-schema/SKILL.md`` (Generation, templates, status tables),
``skills/seo/references/schema-types.md`` and ``scripts/schema_ecommerce_validate.py`` (merchant
listing minimum). MIT.

The suggestions are DATA, not findings and not part of the page: they are stored in the module
block and are never counted as markup the site has. Existing markup is judged by the page checks
(``schema_checks``, which also owns the Product/Offer missing-field rules); this module raises no
finding of its own and only records the gaps of an existing Product as data. Rules of generation:

* only values read from the page are filled in; everything else is a marked placeholder and the
  suggestion is ``complete=False`` with the fields listed in ``missing_fields``;
* HowTo, new FAQPage and every type the reference calls retired are never suggested;
* every suggestion is run through the existing JSON-LD checks (placeholders replaced by
  well-formed fillers) so a generated block cannot fail our own rules;
* no ``AggregateRating``/``Review`` is ever invented.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from seoa.application.analysis.modules import schema_templates as tpl
from seoa.application.analysis.plugin import AnalysisInputs, ModuleResult, register_module
from seoa.application.analysis.types import AnalysisPage
from seoa.domain import Finding
from seoa.domain.parsing.html import ParsedPage, parse_html
from seoa.domain.rules.schema_checks import _present, _types_of, _walk, run_schema_checks

MAX_PAGES = 25
MAX_ITEMS_PER_PAGE = 5

# ------------------------------------------------------------------------------- output model


class SchemaSuggestion(BaseModel):
    url: str
    type: str
    reason: str
    json_ld: str
    complete: bool
    missing_fields: list[str] = Field(default_factory=list)
    validation_issues: list[str] = Field(default_factory=list)  # our own schema rule ids
    rich_result_note: str = ""
    warning: str = ""


class SchemaSuggestions(BaseModel):
    items: list[SchemaSuggestion] = Field(default_factory=list)
    pages_examined: int = 0
    product_gaps: list[dict[str, Any]] = Field(default_factory=list)  # existing Product markup
    notes: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------------------- texts

_WARNING = {
    "en": "Fill in every <fill in: ...> placeholder with real values before publishing.",
    "tr": "Yayınlamadan önce her <doldurun: ...> yer tutucusunu gerçek değerle değiştirin.",
}
# Conservative notes taken from schema-types.md; nothing here promises a ranking or a result.
_NOTES: dict[str, dict[str, str]] = {
    "Organization": {
        "en": "Helps search engines understand the organization's name, logo and profiles. No rich result is guaranteed.",
        "tr": "Arama motorlarının kuruluşun adını, logosunu ve profillerini anlamasına yardımcı olur. Zengin sonuç garanti edilmez.",
    },
    "WebSite": {
        "en": "Names the site for search engines. A SearchAction gives no sitelinks search box benefit, so none is suggested.",
        "tr": "Siteyi arama motorlarına adlandırır. SearchAction'ın site içi arama kutusu faydası yoktur, bu yüzden önerilmedi.",
    },
    "Article": {
        "en": "Helps Google understand headline, author and dates. Google lists no dedicated rich result you can count on.",
        "tr": "Google'ın başlık, yazar ve tarihleri anlamasına yardımcı olur. Güvenebileceğiniz özel bir zengin sonuç yoktur.",
    },
    "Product": {
        "en": "Product snippets and merchant listings need name, image and an offer with price, currency and availability that match the page.",
        "tr": "Ürün snippet'ları ve satıcı listeleri, sayfayla uyuşan ad, görsel ve fiyat, para birimi, stok durumu olan bir teklif ister.",
    },
    "LocalBusiness": {
        "en": "Business details must match what the page shows (name, address, phone). Eligibility for local features is not guaranteed.",
        "tr": "İşletme bilgileri sayfada görünenle (ad, adres, telefon) uyuşmalı. Yerel özelliklere uygunluk garanti edilmez.",
    },
    "BreadcrumbList": {
        "en": "Can show the breadcrumb trail in results (desktop only since January 2025).",
        "tr": "Sonuçlarda gezinme yolunu gösterebilir (Ocak 2025'ten beri yalnız masaüstünde).",
    },
}
_REASONS: dict[str, dict[str, str]] = {
    "Organization": {
        "en": "Home page without Organization markup.",
        "tr": "Ana sayfada Organization işaretlemesi yok.",
    },
    "WebSite": {
        "en": "Home page without WebSite markup.",
        "tr": "Ana sayfada WebSite işaretlemesi yok.",
    },
    "Article": {
        "en": "The page looks like an article or blog post (type, byline/date metadata or blog path) and has no Article markup.",
        "tr": "Sayfa bir makale/blog yazısına benziyor (tür, yazar/tarih üst verisi veya blog yolu) ve Article işaretlemesi yok.",
    },
    "Product": {
        "en": "The page looks like a product page (product metadata, or a price with an add-to-cart control) and has no Product markup.",
        "tr": "Sayfa bir ürün sayfasına benziyor (ürün üst verisi veya sepete ekle ile fiyat) ve Product işaretlemesi yok.",
    },
    "LocalBusiness": {
        "en": "The page shows a phone number and an address but no LocalBusiness markup (heuristic).",
        "tr": "Sayfada telefon ve adres var ama LocalBusiness işaretlemesi yok (sezgisel).",
    },
    "BreadcrumbList": {
        "en": "The page is two or more levels deep and has no BreadcrumbList. Names are derived from the URL: check them.",
        "tr": "Sayfa iki veya daha fazla seviye derinde ve BreadcrumbList yok. Adlar URL'den türetildi: kontrol edin.",
    },
}

# ------------------------------------------------------------------------------- signals

_PHONE = re.compile(r"(?<![\w])(\+?\d[\d\s().-]{7,16}\d)(?![\w])")
_ADDRESS = re.compile(
    r"\b(?:street|st\.|avenue|ave\.|road|rd\.|address|cad\.|cadde|sok\.|sokak|mah\.|mahalle|adres)\b",
    re.I,
)
_CART = re.compile(r"add to (?:cart|basket|bag)|buy now|sepete ekle|satın al", re.I)
_PRICE = re.compile(r"(?:[$€£₺]\s?\d[\d.,]*|\d[\d.,]*\s?(?:₺|TL|TRY|USD|EUR|€|\$))")
_BLOG_PATH = re.compile(r"/(?:blog|news|haber|haberler|makale|yazi|yazilar|articles?)(?:/|$)", re.I)
_CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "₺": "TRY"}


def _meta(parsed: ParsedPage, *keys: str) -> str:
    wanted = {k.lower() for k in keys}
    for name, prop, content in parsed.meta_tags:
        if (name.lower() in wanted or prop.lower() in wanted) and content.strip():
            return content.strip()
    return ""


def _abs(value: str, base: str) -> str | None:
    from urllib.parse import urljoin

    if not value:
        return None
    u = urljoin(base, value)
    return u if u.lower().startswith(("http://", "https://")) else None


def _path(url: str) -> str:
    return urlparse(url).path or "/"


def _site_name(parsed: ParsedPage) -> str | None:
    return parsed.og.get("og:site_name", "").strip()[:100] or None


def _title(parsed: ParsedPage) -> str:
    return (parsed.h1[0] if parsed.h1 else parsed.title).strip()


def _present_types(parsed: ParsedPage) -> set[str]:
    return set(parsed.schema_types)


def _is_article(parsed: ParsedPage, url: str) -> bool:
    if parsed.og.get("og:type", "").lower() == "article":
        return True
    if _meta(parsed, "article:published_time"):
        return True
    return bool(_BLOG_PATH.search(_path(url)) and parsed.h1 and parsed.word_count >= 300)


def _is_product(parsed: ParsedPage) -> bool:
    if parsed.og.get("og:type", "").lower() in ("product", "og:product"):
        return True
    if _meta(parsed, "product:price:amount", "og:price:amount"):
        return True
    text = parsed.visible_text[:20000]
    return bool(_CART.search(text) and _PRICE.search(text))


def _telephone(parsed: ParsedPage) -> str | None:
    m = _PHONE.search(parsed.visible_text[:20000])
    return m.group(1).strip() if m else None


def _breadcrumb_items(url: str, parsed: ParsedPage, lang: str) -> list[tuple[str, str]]:
    p = urlparse(url)
    origin = f"{p.scheme}://{p.netloc}"
    segs = [s for s in p.path.split("/") if s]
    items = [("Ana sayfa" if lang == "tr" else "Home", origin + "/")]
    acc = ""
    for i, seg in enumerate(segs):
        acc += f"/{seg}"
        last = i == len(segs) - 1
        name = (
            _title(parsed)
            if last and _title(parsed)
            else re.sub(r"[-_]+", " ", seg).strip().title()
        )
        items.append((name[:100], f"{origin}{acc}" + ("" if last else "/")))
    return items


# ------------------------------------------------------------------------------- validation

_URL_KEYS = {"url", "image", "logo", "sameas", "item", "mainentityofpage"}
_DATE_KEYS = {"datepublished", "datemodified"}


def _fill(data: Any, key: str = "") -> Any:
    """Replace placeholders by well-formed fillers so the structure can be validated."""
    if isinstance(data, dict):
        return {k: _fill(v, k) for k, v in data.items()}
    if isinstance(data, list):
        return [_fill(v, key) for v in data]
    if tpl.is_placeholder(data):
        lk = key.lower()
        if lk in _URL_KEYS:
            return "https://example.org/x"
        if lk in _DATE_KEYS:
            return "2026-01-01"
        if lk == "price":
            return "10"
        return "Example"
    return data


def validate_json_ld(text: str) -> list[str]:
    """Rule ids our own schema checks raise on ``text`` (placeholders filled in); [] = clean."""
    try:
        data = json.loads(text)
    except ValueError:
        return ["invalid-jsonld"]
    doc = json.dumps(_fill(data))
    # </script> inside a value cannot occur: we escape "<" when serialising for the page.
    safe = doc.replace("<", "\\u003c")
    html = f'<html><head><script type="application/ld+json">{safe}</script></head></html>'
    parsed = parse_html(html, "https://example.org/")
    return sorted({f.id for f in run_schema_checks(parsed, "https://example.org/").findings})


def _serialise(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------------------- suggestions


def _suggestion(url: str, kind: str, data: dict[str, Any], lang: str) -> SchemaSuggestion:
    assert kind not in tpl.NEVER_SUGGEST
    missing = tpl.placeholder_paths(data)
    text = _serialise(data)
    return SchemaSuggestion(
        url=url,
        type=kind,
        reason=_REASONS[kind if kind != "BlogPosting" else "Article"][lang],
        json_ld=text,
        complete=not missing,
        missing_fields=missing,
        validation_issues=validate_json_ld(text),
        rich_result_note=_NOTES[kind if kind != "BlogPosting" else "Article"][lang],
        warning=_WARNING[lang] if missing else "",
    )


def suggest_for_page(page: AnalysisPage, lang: str = "en") -> list[SchemaSuggestion]:
    parsed = page.parsed
    if parsed is None or page.error or page.status is None or page.status >= 400:
        return []
    url = page.effective_url
    present = _present_types(parsed)
    out: list[SchemaSuggestion] = []
    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    description = parsed.meta_description.strip()[:300] or None
    image = _abs(parsed.og.get("og:image", ""), url)
    site = _site_name(parsed)

    if _path(url) == "/":
        if not present & {"Organization", "LocalBusiness"}:
            out.append(
                _suggestion(
                    url,
                    "Organization",
                    tpl.organization(name=site, url=origin + "/", logo=None, lang=lang),
                    lang,
                )
            )
        if "WebSite" not in present:
            out.append(
                _suggestion(
                    url, "WebSite", tpl.website(name=site, url=origin + "/", lang=lang), lang
                )
            )

    if (
        not present & {"Article", "BlogPosting", "NewsArticle"}
        and _is_article(parsed, url)
        and _title(parsed)
    ):
        kind = "BlogPosting" if "/blog" in _path(url).lower() else "Article"
        published = _meta(parsed, "article:published_time")
        data = tpl.article(
            kind=kind,
            headline=_title(parsed),
            url=url,
            description=description,
            image=image,
            author=_meta(parsed, "author", "article:author") or None,
            published=published[:25] if re.match(r"^\d{4}-\d{2}-\d{2}", published) else None,
            publisher=site,
            lang=lang,
        )
        out.append(_suggestion(url, kind, data, lang))

    if "Product" not in present and _is_product(parsed) and _title(parsed):
        raw_price = _meta(parsed, "product:price:amount", "og:price:amount")
        price = raw_price if re.fullmatch(r"\d+(?:[.,]\d{1,2})?", raw_price) else None
        cur = _meta(parsed, "product:price:currency", "og:price:currency").upper()
        currency = cur if re.fullmatch(r"[A-Z]{3}", cur) else None
        data = tpl.product(
            name=_title(parsed),
            url=url,
            description=description,
            image=image,
            price=price.replace(",", ".") if price else None,
            currency=currency,
            lang=lang,
        )
        out.append(_suggestion(url, "Product", data, lang))

    if (
        not present & {"LocalBusiness", "Organization"}
        and _ADDRESS.search(parsed.visible_text[:20000])
        and (tel := _telephone(parsed))
        and not _is_product(parsed)
    ):
        out.append(
            _suggestion(
                url,
                "LocalBusiness",
                tpl.local_business(name=site, url=url, telephone=tel, lang=lang),
                lang,
            )
        )

    if "BreadcrumbList" not in present and len([s for s in _path(url).split("/") if s]) >= 2:
        out.append(
            _suggestion(
                url,
                "BreadcrumbList",
                tpl.breadcrumb_list(_breadcrumb_items(url, parsed, lang)),
                lang,
            )
        )

    return out[:MAX_ITEMS_PER_PAGE]


# ------------------------------------------------------------------------------- Product findings

_OFFER_FIELDS = ("price", "priceCurrency", "availability")


def product_gaps(page: AnalysisPage) -> list[str]:
    """Merchant-listing fields missing from Product markup that already exists on the page."""
    parsed = page.parsed
    if parsed is None:
        return []
    missing: list[str] = []
    for block in parsed.jsonld:
        if block.error or block.data is None:
            continue
        nodes: list[dict[str, Any]] = []
        _walk(block.data, nodes)
        for node in nodes:
            if "Product" not in _types_of(node):
                continue
            for prop in ("name", "image"):
                if not _present(node, prop):
                    missing.append(prop)
            offers = node.get("offers")
            offer_list = [
                o for o in (offers if isinstance(offers, list) else [offers]) if isinstance(o, dict)
            ]
            if not offer_list:
                missing.append("offers")
                continue
            for prop in _OFFER_FIELDS:
                if not any(_present(o, prop) for o in offer_list):
                    missing.append(f"offers.{prop}")
    return list(dict.fromkeys(missing))


class SchemaSuggestModule:
    name = "schema_suggest"
    kind = "schema_suggestions"
    timeout_s = 15.0

    async def run(self, inp: AnalysisInputs) -> ModuleResult:
        lang = "tr" if inp.output_lang == "tr" else "en"
        result = SchemaSuggestions()
        findings: list[Finding] = []  # none: the page rules live in schema_checks
        seen: set[tuple[str, str]] = set()
        examined = 0
        for page in inp.pages[:MAX_PAGES]:
            if page.parsed is None:
                continue
            examined += 1
            gaps = product_gaps(page)
            if gaps:
                result.product_gaps.append({"url": page.url, "missing": gaps})
            for s in suggest_for_page(page, lang):
                # Organization/WebSite are site-level: one suggestion is enough
                if (
                    s.type in ("Organization", "WebSite", "LocalBusiness")
                    and (s.type, "site") in seen
                ):
                    continue
                if s.type in ("Organization", "WebSite"):
                    seen.add((s.type, "site"))
                result.items.append(s)
        result.pages_examined = examined
        if not result.items:
            result.notes.append("no-missing-types-detected")
        result.notes.append("suggestions-are-not-part-of-the-page")
        return ModuleResult(kind=self.kind, data=result, findings=findings)


register_module(SchemaSuggestModule())

__all__ = [
    "SchemaSuggestModule",
    "SchemaSuggestion",
    "SchemaSuggestions",
    "product_gaps",
    "suggest_for_page",
    "validate_json_ld",
]
