"""ContentInput: the only page-derived material the LLM sees (belge 03 s.4).

Raw HTML never reaches the model. Trusted ``facts`` come from code; everything else is
untrusted and wrapped in ``<untrusted_page_content>`` envelopes with the closing tag escaped.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any
from urllib.parse import urlparse

from lxml import html as lh
from pydantic import BaseModel, Field

MAX_MAIN = 12_000
HEAD_KEEP, TAIL_KEEP = 9_000, 3_000
MAX_OUTLINE = 40
MAX_LINKS = 60
MAX_ANCHOR = 80
_CLOSE = re.compile(r"<\s*/\s*untrusted_page_content\s*>?", re.I)
_WS = re.compile(r"\s+")
_ZONE_TAGS = {"header": "header", "nav": "nav", "footer": "footer", "aside": "aside"}
_ZONE_ROLES = {
    "banner": "header",
    "navigation": "nav",
    "contentinfo": "footer",
    "complementary": "aside",
}
_ZONE_CLASS = re.compile(
    r"(^|[\s_-])(footer|site-footer|navbar|main-nav|topbar|site-header|menu)([\s_-]|$)", re.I
)


class ChromeLink(BaseModel):
    anchor: str
    href_path: str
    zone: str


class ContentInput(BaseModel):
    url: str
    lang: str | None = None
    page_type: str = "other"
    facts: dict[str, Any] = Field(default_factory=dict)  # trusted
    title: str = ""
    h1: str = ""
    outline: list[str] = Field(default_factory=list)
    main_text: str = ""
    byline: str = ""
    chrome_links: list[ChromeLink] = Field(default_factory=list)

    def field_text(self, field: str) -> str:
        """The text a quote must be found in (V3 is verified against exactly this)."""
        if field == "main_text":
            return self.main_text
        if field == "byline":
            return self.byline
        if field == "title":
            return self.title
        if field == "h1":
            return self.h1
        if field == "outline":
            return "\n".join(self.outline)
        if field == "chrome_link":
            return self._chrome_lines()
        return ""

    def _chrome_lines(self) -> str:
        """One line per link, exactly as the envelope shows it to the model."""
        return "\n".join(f"[{c.zone}] {c.anchor} -> {c.href_path}" for c in self.chrome_links)

    def content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"url"})
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    def envelope(self) -> str:
        """User message: every page-derived field inside an untrusted envelope."""
        parts = []
        for name in ("title", "h1", "byline", "outline", "main_text", "chrome_links"):
            if name == "outline":
                value = "\n".join(self.outline)
            elif name == "chrome_links":
                value = self._chrome_lines()
            else:
                value = str(getattr(self, name))
            parts.append(wrap_untrusted(name if name != "chrome_links" else "chrome_link", value))
        return "\n".join(parts)


def escape_envelope(text: str) -> str:
    return _CLOSE.sub("‹/untrusted_page_content›", text)


def wrap_untrusted(field: str, text: str) -> str:
    return f'<untrusted_page_content field="{field}">\n{escape_envelope(text)}\n</untrusted_page_content>'


def _clean(s: str | None) -> str:
    return _WS.sub(" ", unicodedata.normalize("NFC", s or "")).strip()


def _jsonld(doc: Any) -> list[Any]:
    out: list[Any] = []
    for node in doc.xpath('//script[@type="application/ld+json"]'):
        try:
            data = json.loads(node.text_content())
        except (json.JSONDecodeError, ValueError):
            continue
        out.extend(data if isinstance(data, list) else [data])
    flat: list[Any] = []

    def walk(n: Any) -> None:
        if isinstance(n, dict):
            flat.append(n)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    for item in out:
        walk(item)
    return flat


def _types(nodes: list[Any]) -> list[str]:
    seen: list[str] = []
    for n in nodes:
        t = n.get("@type")
        for x in t if isinstance(t, list) else [t]:
            if isinstance(x, str) and x not in seen:
                seen.append(x)
    return seen[:20]


def _author(nodes: list[Any], doc: Any) -> str:
    names: list[str] = []
    for n in nodes:
        a = n.get("author")
        for x in a if isinstance(a, list) else [a]:
            if isinstance(x, str):
                names.append(x)
            elif isinstance(x, dict) and isinstance(x.get("name"), str):
                names.append(x["name"])
    for sel in (
        '//meta[@name="author"]/@content',
        '//a[@rel="author"]',
        '//*[contains(@class,"byline")]',
    ):
        for el in doc.xpath(sel):
            names.append(el if isinstance(el, str) else el.text_content())
    return _clean(" | ".join(dict.fromkeys(_clean(n) for n in names if _clean(n))))[:300]


def _dates(nodes: list[Any], doc: Any) -> dict[str, str | None]:
    pub = mod = None
    for n in nodes:
        pub = pub or n.get("datePublished")
        mod = mod or n.get("dateModified")
    for prop, slot in (("article:published_time", "pub"), ("article:modified_time", "mod")):
        v = doc.xpath(f'//meta[@property="{prop}"]/@content')
        if v and slot == "pub":
            pub = pub or v[0]
        if v and slot == "mod":
            mod = mod or v[0]
    if not pub:
        t = doc.xpath("//time/@datetime")
        pub = t[0] if t else None
    return {
        "published": pub if isinstance(pub, str) else None,
        "modified": mod if isinstance(mod, str) else None,
    }


def _zone(el: Any) -> str | None:
    for anc in el.iterancestors():
        tag = anc.tag if isinstance(anc.tag, str) else ""
        if tag in _ZONE_TAGS:
            return _ZONE_TAGS[tag]
        role = anc.get("role")
        if role in _ZONE_ROLES:
            return _ZONE_ROLES[role]
        cls = (anc.get("class") or "") + " " + (anc.get("id") or "")
        if _ZONE_CLASS.search(cls):
            return "footer" if "footer" in cls.lower() else "nav"
    return None


def _main_text(html: str, doc: Any) -> str:
    text = ""
    if not html.strip():
        return ""
    try:
        import trafilatura

        text = (
            trafilatura.extract(
                html, include_comments=False, include_tables=False, favor_recall=True
            )
            or ""
        )
    except Exception:  # noqa: BLE001 - trafilatura is best-effort; fall back below
        text = ""
    if len(text) < 200:
        clone: Any = lh.fromstring(html)
        for bad in clone.xpath(
            "//script|//style|//noscript|//nav|//header|//footer|//aside|//template"
        ):
            bad.drop_tree()
        body = clone.xpath("//body")
        text = _clean((body[0] if body else clone).text_content())
    text = text.strip()
    if len(text) > MAX_MAIN:
        text = text[:HEAD_KEEP] + "\n[...]\n" + text[-TAIL_KEEP:]
    return text


def build_content_input(
    html: str,
    url: str,
    headers: dict[str, str] | None = None,
    *,
    lang: str | None = None,
    facts: dict[str, Any] | None = None,
) -> ContentInput:
    doc: Any = lh.fromstring(html if html.strip() else "<html></html>")
    nodes = _jsonld(doc)
    types = _types(nodes)
    host = (urlparse(url).hostname or "").lower()

    links: list[ChromeLink] = []
    seen_links: set[tuple[str, str]] = set()
    ext_main = 0
    contact: dict[str, Any] = {}
    for a in doc.xpath("//a[@href]"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "data:")):
            continue
        scheme = href.split(":", 1)[0].lower() if ":" in href.split("/")[0] else ""
        if scheme in ("mailto", "tel"):
            contact[scheme] = True
            path = f"{scheme}:"
        else:
            path = urlparse(href).path or "/"
        zone = _zone(a)
        if zone is None:
            h = (urlparse(href).hostname or "").lower()
            if h and h != host and scheme not in ("mailto", "tel"):
                ext_main += 1
            continue
        anchor = (
            _clean(a.text_content())[:MAX_ANCHOR]
            or _clean(a.get("aria-label") or a.get("title"))[:MAX_ANCHOR]
        )
        key = (anchor, path)
        if not anchor or key in seen_links or len(links) >= MAX_LINKS:
            continue
        seen_links.add(key)
        links.append(ChromeLink(anchor=anchor, href_path=path, zone=zone))
    for n in nodes:
        if n.get("contactPoint") or n.get("telephone") or n.get("email") or n.get("address"):
            contact["jsonld"] = True
    # contact page links count too, but classification of those stays with the LLM

    main = _main_text(html, doc)
    h1 = _clean(" ".join(doc.xpath("(//h1)[1]//text()")))[:200]
    title = _clean(" ".join(doc.xpath("//title//text()")))[:200]
    outline = [
        f"{h.tag.upper()}: {_clean(h.text_content())[:120]}"
        for h in doc.xpath("//h1|//h2|//h3|//h4|//h5|//h6")
        if _clean(h.text_content())
    ][:MAX_OUTLINE]

    path = urlparse(url).path or "/"
    if "Product" in types:
        page_type = "product"
    elif {"Article", "BlogPosting", "NewsArticle"} & set(types):
        page_type = "article"
    elif path in ("", "/"):
        page_type = "home"
    else:
        page_type = "other"

    base_facts: dict[str, Any] = {
        "https": url.lower().startswith("https://"),
        "word_count": len(main.split()),
        "heading_count": len(outline),
        "schema_types": types,
        "dates": _dates(nodes, doc),
        "outbound_external_links_in_main": ext_main,
        "contact": contact,
    }
    base_facts.update(facts or {})
    return ContentInput(
        url=url,
        lang=lang or (doc.get("lang") or None),
        page_type=page_type,
        facts=base_facts,
        title=title,
        h1=h1,
        outline=outline,
        main_text=main,
        byline=_author(nodes, doc),
        chrome_links=links,
    )
