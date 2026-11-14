"""JSON-LD builders for the schema suggestions (belge 12 A7).

Adapted from the upstream project ``skills/seo-schema/SKILL.md`` ("Common Schema Templates", "Generation":
*include only truthful, verifiable data; use placeholders clearly marked for the user to fill*),
``skills/seo/references/schema-types.md`` (key properties per type) and
``scripts/schema_generate.py`` (``@context: https://schema.org``, absolute URLs, ``_strip_nones``).

Only values read from the page are filled in. Everything else is an explicit placeholder
``<doldurun: ...>`` / ``<fill in: ...>`` that the user must replace; ``is_placeholder`` finds them.
Types Google retired (HowTo, FAQ rich results, ...) have no builder on purpose.
"""

from __future__ import annotations

from typing import Any

CONTEXT = "https://schema.org"
PLACEHOLDER_OPEN = {"tr": "<doldurun: ", "en": "<fill in: "}
_PLACEHOLDER_MARKS = tuple(PLACEHOLDER_OPEN.values())

# Types that are never suggested (the upstream project schema-types.md "Deprecated: Never recommend" and
# the FAQPage decision). Used by the module as a hard filter and by the tests.
NEVER_SUGGEST = frozenset(
    {
        "HowTo",
        "FAQPage",
        "SpecialAnnouncement",
        "CourseInfo",
        "EstimatedSalary",
        "LearningVideo",
        "ClaimReview",
        "VehicleListing",
    }
)


def placeholder(what: str, lang: str = "en") -> str:
    return f"{PLACEHOLDER_OPEN.get(lang, PLACEHOLDER_OPEN['en'])}{what}>"


def is_placeholder(value: object) -> bool:
    return isinstance(value, str) and value.startswith(_PLACEHOLDER_MARKS)


def placeholder_paths(data: Any, prefix: str = "") -> list[str]:
    """Dotted paths of every placeholder value in a JSON-LD structure."""
    out: list[str] = []
    if isinstance(data, dict):
        for k, v in data.items():
            if k.startswith("@"):
                continue
            out.extend(placeholder_paths(v, f"{prefix}{k}."))
    elif isinstance(data, list):
        for i, v in enumerate(data):
            out.extend(placeholder_paths(v, f"{prefix}{i}."))
    elif is_placeholder(data):
        out.append(prefix.rstrip("."))
    return out


def strip_nones(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if v not in (None, "", [], {})}


def _ph(what: str, lang: str) -> str:
    return placeholder(what, lang)


def organization(
    *, name: str | None, url: str, logo: str | None, lang: str = "en"
) -> dict[str, Any]:
    return {
        "@context": CONTEXT,
        "@type": "Organization",
        "name": name or _ph("organization name" if lang == "en" else "kuruluş adı", lang),
        "url": url,
        "logo": logo or _ph("absolute logo URL" if lang == "en" else "logo URL'si (mutlak)", lang),
        "sameAs": [_ph("social profile URL" if lang == "en" else "sosyal profil URL'si", lang)],
    }


def website(*, name: str | None, url: str, lang: str = "en") -> dict[str, Any]:
    return {
        "@context": CONTEXT,
        "@type": "WebSite",
        "name": name or _ph("site name" if lang == "en" else "site adı", lang),
        "url": url,
    }


def article(
    *,
    kind: str,
    headline: str,
    url: str,
    description: str | None,
    image: str | None,
    author: str | None,
    published: str | None,
    publisher: str | None,
    lang: str = "en",
) -> dict[str, Any]:
    tr = lang == "tr"
    return strip_nones(
        {
            "@context": CONTEXT,
            "@type": kind,
            "headline": headline[:110],
            "description": description,
            "mainEntityOfPage": url,
            "image": image
            or _ph("absolute image URL" if not tr else "görsel URL'si (mutlak)", lang),
            "author": {
                "@type": "Person",
                "name": author or _ph("author name" if not tr else "yazar adı", lang),
            },
            "datePublished": published
            or _ph(
                "ISO 8601 date, e.g. 2026-01-31" if not tr else "ISO 8601 tarih, örn. 2026-01-31",
                lang,
            ),
            "publisher": {
                "@type": "Organization",
                "name": publisher or _ph("publisher name" if not tr else "yayıncı adı", lang),
            },
        }
    )


def product(
    *,
    name: str,
    url: str,
    description: str | None,
    image: str | None,
    price: str | None,
    currency: str | None,
    lang: str = "en",
) -> dict[str, Any]:
    tr = lang == "tr"
    return strip_nones(
        {
            "@context": CONTEXT,
            "@type": "Product",
            "name": name,
            "description": description,
            "image": image
            or _ph("absolute image URL" if not tr else "görsel URL'si (mutlak)", lang),
            "sku": _ph("product SKU" if not tr else "ürün SKU", lang),
            "offers": {
                "@type": "Offer",
                "url": url,
                "price": price
                or _ph("price, digits only" if not tr else "fiyat (yalnız rakam)", lang),
                "priceCurrency": currency
                or _ph(
                    "ISO 4217 currency, e.g. USD" if not tr else "ISO 4217 para birimi, örn. TRY",
                    lang,
                ),
                "availability": _ph(
                    "https://schema.org/InStock or OutOfStock"
                    if not tr
                    else "https://schema.org/InStock veya OutOfStock",
                    lang,
                ),
            },
        }
    )


def local_business(
    *, name: str | None, url: str, telephone: str | None, lang: str = "en"
) -> dict[str, Any]:
    tr = lang == "tr"
    return strip_nones(
        {
            "@context": CONTEXT,
            "@type": "LocalBusiness",
            "name": name or _ph("business name" if not tr else "işletme adı", lang),
            "url": url,
            "telephone": telephone or _ph("phone number" if not tr else "telefon numarası", lang),
            "address": {
                "@type": "PostalAddress",
                "streetAddress": _ph("street address" if not tr else "açık adres", lang),
                "addressLocality": _ph("city" if not tr else "şehir", lang),
                "addressCountry": _ph(
                    "ISO 3166-1 country code" if not tr else "ISO 3166-1 ülke kodu", lang
                ),
            },
        }
    )


def breadcrumb_list(items: list[tuple[str, str]]) -> dict[str, Any]:
    """``items``: (name, absolute url) from the home page down to the current page."""
    return {
        "@context": CONTEXT,
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": n, "item": u}
            for i, (n, u) in enumerate(items, 1)
        ],
    }
