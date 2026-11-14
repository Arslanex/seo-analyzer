"""Report sections for local SEO, the suggested sitemap and domain authority (belge 12 C4/C5/B2).

Same contract as ``suite``: a section is measured (with data) or not measured (with a reason).
Page-derived text goes through ``clean_text`` and is autoescaped by the template.
"""

from __future__ import annotations

import re
from typing import Any

from seoa.application.reporting import schema as s
from seoa.application.reporting.suite import _c, _label, _load, _nm, _why
from seoa.domain import AuditRecord
from seoa.domain.i18n import t
from seoa.domain.text import clean_text

LIST_CAP = 20
XML_PREVIEW_URLS = 200
_BLOCK = re.compile(r"  <url>.*?</url>\n", re.S)


def _yn(lang: str, v: bool) -> str:
    return t(lang, "idx.yes" if v else "idx.no")


# --------------------------------------------------------------------------- local


def local_section(rec: AuditRecord, lang: str) -> s.LocalSection:
    from seoa.application.analysis.modules.local import LocalSeo

    data = _load(rec, "local", LocalSeo)
    if isinstance(data, str):
        return s.LocalSection(**_nm(lang, _why(rec, "local") if data == "suite-no-data" else data))
    if not data.applicable:
        return s.LocalSection(**_nm(lang, _why(rec, "local")))
    facts = [
        s.KV(label=t(lang, "local.fact.pages"), value=str(data.pages_scanned)),
        s.KV(label=t(lang, "local.fact.tel"), value=_yn(lang, data.has_tel_link)),
        s.KV(label=t(lang, "local.fact.map"), value=_yn(lang, data.has_map_embed)),
    ]
    if data.business_types:
        facts.append(
            s.KV(
                label=t(lang, "local.fact.types"),
                value=", ".join(_c(x, 40) for x in data.business_types[:LIST_CAP]),
            )
        )
    if data.names:
        facts.append(
            s.KV(
                label=t(lang, "local.fact.names"),
                value=", ".join(_c(x, 80) for x in data.names[:5]),
            )
        )
    facts.append(
        s.KV(
            label=t(lang, "local.fact.signals"),
            value=", ".join(_label(lang, "local.signal", x) for x in data.signals) or "—",
        )
    )
    return s.LocalSection(
        status="measured",
        facts=facts,
        phones=[
            s.LocalPhoneRow(
                number=_c(p.number, 30),
                formats=", ".join(_c(f, 30) for f in p.formats),
                sources=", ".join(_label(lang, "local.source", x) for x in p.sources),
                pages=len(p.pages),
            )
            for p in data.phones[:LIST_CAP]
        ],
        addresses=[
            s.LocalAddressRow(
                text=_c(a.text, 200),
                source=_label(lang, "local.source", a.source),
                pages=len(a.pages),
            )
            for a in data.addresses[:LIST_CAP]
        ],
        issues=[
            s.LocalIssueRow(
                label=_label(lang, "local.issue", i.code),
                values=" | ".join(_c(v, 120) for v in i.values),
                pages=", ".join(_c(u, 200) for u in i.pages[:3]),
            )
            for i in data.inconsistencies[:LIST_CAP]
        ],
        notes=[_label(lang, "local.note", n) for n in data.notes],
        note=t(lang, "local.intro"),
    )


# --------------------------------------------------------------------------- sitemap


def _preview(xml: str) -> str:
    blocks = _BLOCK.findall(xml)
    head = '<?xml version="1.0" encoding="UTF-8"?>\n'
    m = re.search(r"<urlset[^>]*>\n", xml)
    open_tag = m.group(0) if m else "<urlset>\n"
    return clean_text(head + open_tag + "".join(blocks[:XML_PREVIEW_URLS]) + "</urlset>\n")


def sitemap_gen_section(rec: AuditRecord, lang: str) -> s.SitemapGenSection:
    from seoa.application.analysis.modules.sitemap_gen import SitemapGenerated

    data = _load(rec, "sitemap_generated", SitemapGenerated)
    if isinstance(data, str):
        return s.SitemapGenSection(
            **_nm(lang, _why(rec, "sitemap_generated") if data == "suite-no-data" else data)
        )
    facts = [
        s.KV(label=t(lang, "smg.fact.urls"), value=str(data.urls_total)),
        s.KV(label=t(lang, "smg.fact.lastmod"), value=str(data.with_lastmod)),
        s.KV(label=t(lang, "smg.fact.sample"), value=str(data.pages_in_sample)),
        s.KV(label=t(lang, "smg.fact.existing"), value=_yn(lang, data.existing_sitemap)),
    ]
    return s.SitemapGenSection(
        status="measured",
        facts=facts,
        xml_preview=_preview(data.xml),
        urls_total=data.urls_total,
        urls_shown=min(data.urls_total, XML_PREVIEW_URLS),
        missing=[_c(u, 300) for u in data.missing_from_sitemap[:LIST_CAP]],
        missing_total=data.missing_total,
        not_indexable=[
            s.KV(label=_c(x.url, 300), value=_label(lang, "smg.reason", x.reason))
            for x in data.in_sitemap_not_indexable[:LIST_CAP]
        ],
        not_indexable_total=data.in_sitemap_not_indexable_total,
        excluded=[
            s.KV(label=_c(x.url, 300), value=_label(lang, "smg.reason", x.reason))
            for x in data.excluded[:LIST_CAP]
        ],
        excluded_total=data.excluded_total,
        download_href=f"/v1/audits/{rec.id}/sitemap.xml",
        note=t(lang, "smg.note"),
        truncated=data.truncated,
    )


# --------------------------------------------------------------------------- authority


def authority_section(rec: AuditRecord, lang: str) -> s.AuthoritySection:
    from seoa.application.analysis.modules.authority import AuthoritySignal

    data = _load(rec, "authority", AuthoritySignal)
    if isinstance(data, str):
        return s.AuthoritySection(
            **_nm(lang, _why(rec, "authority") if data == "suite-no-data" else data)
        )
    items = [s.KV(label=t(lang, "auth.domain"), value=_c(data.domain, 120))]
    if data.page_rank_decimal is not None:
        items.append(s.KV(label=t(lang, "auth.pr"), value=f"{data.page_rank_decimal:.2f} / 10"))
    if data.rank is not None:
        items.append(s.KV(label=t(lang, "auth.rank"), value=f"{data.rank:,}".replace(",", ".")))
    return s.AuthoritySection(status="measured", items=items, note=t(lang, "auth.note"))


def build_extra(rec: AuditRecord, lang: str) -> dict[str, Any]:
    from seoa.application.reporting.rankings import rankings_section

    return {
        "rankings": rankings_section(rec, lang),
        "local": local_section(rec, lang),
        "sitemap_gen": sitemap_gen_section(rec, lang),
        "authority": authority_section(rec, lang),
    }
