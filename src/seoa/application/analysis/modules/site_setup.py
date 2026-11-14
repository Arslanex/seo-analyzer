"""Site setup (belge 12 A2): redirect matrix, soft-404, custom 404, compression, cache validators,
header disclosure, and well-known files (favicon, manifest, security.txt, ads.txt, humans.txt).

At most ``MAX_REQUESTS`` requests, all through the safe fetcher. The http->https and www/apex
redirects are *measured* here (the matrix) but not turned into findings: the transport checks
already own ``http-no-https-redirect``, ``http-https-redirect-temporary`` and
``www-not-consolidated``, and one problem must not be reported twice.
``robots.txt`` and the sitemap belong to other checks. HTTP version is not observable through
aiohttp, so it is reported as ``unknown`` rather than guessed.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import secrets
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from pydantic import BaseModel, Field

from seoa.application.analysis.plugin import AnalysisInputs, ModuleResult, register_module
from seoa.application.ports import RawResponse
from seoa.domain import Category, Finding, NotChecked, Severity
from seoa.domain.rules.registry import CheckDef, make_finding, register, register_messages
from seoa.domain.text import decode_body

MAX_REQUESTS = 12
_PAGE_BYTES = 200_000
_SMALL = 4096
_T = Category.TECHNICAL

# --------------------------------------------------------------------------- rules
# (id, severity, heuristic, effort, impact)
_SPECS: tuple[tuple[str, Severity, bool, str, str], ...] = (
    ("trailing-slash-duplicate", Severity.MEDIUM, False, "S", "medium"),
    ("uppercase-path-duplicate", Severity.LOW, False, "S", "low"),
    ("index-file-duplicate", Severity.LOW, False, "S", "low"),
    ("soft-404", Severity.HIGH, False, "M", "high"),
    ("no-custom-404", Severity.LOW, True, "S", "low"),
    ("html-not-compressed", Severity.MEDIUM, False, "S", "medium"),
    ("no-cache-validators", Severity.LOW, True, "S", "low"),
    ("server-version-disclosed", Severity.INFO, False, "S", "low"),
    ("favicon-missing", Severity.LOW, False, "S", "low"),
    ("manifest-invalid", Severity.LOW, False, "S", "low"),
    ("security-txt-missing", Severity.INFO, False, "S", "low"),
)
for _id, _sev, _heur, _eff, _imp in _SPECS:
    register(
        CheckDef(
            id=_id,
            category=_T,
            severity=_sev,
            scope="site",
            heuristic=_heur,
            effort_default=_eff,  # type: ignore[arg-type]
            impact_default=_imp,  # type: ignore[arg-type]
            failure_check_key=f"fail.{_id}",
            leading_indicator_key=f"lead.{_id}",
        )
    )

# id -> (finding EN/TR, recommendation EN/TR, failure-check EN/TR, leading-indicator EN/TR)
_MSG: dict[str, tuple[str, str, str, str, str, str, str, str]] = {
    "trailing-slash-duplicate": (
        "The same page answers with 200 both with and without a trailing slash and no canonical separates them.",
        "Aynı sayfa hem sondaki eğik çizgiyle hem de çizgisiz 200 yanıtı veriyor ve aralarını ayıran bir canonical yok.",
        "Redirect one form to the other with a 301 (or set a self-referencing canonical) and link to one form only.",
        "Biçimlerden birini 301 ile diğerine yönlendirin (veya kendine işaret eden canonical ekleyin) ve yalnızca tek biçime bağlanın.",
        "Requesting the other form redirects (301) or carries a canonical to the preferred URL.",
        "Diğer biçim istendiğinde 301 yönlendirmesi veya tercih edilen URL'ye canonical dönüyor.",
        "Duplicate URL variants of the same page in Search Console's page indexing report.",
        "Search Console sayfa dizinleme raporunda aynı sayfanın yinelenen URL varyantları.",
    ),
    "uppercase-path-duplicate": (
        "The page is also reachable with an upper-case path and both answer with 200.",
        "Sayfa büyük harfli yolla da erişilebiliyor ve ikisi de 200 yanıtı veriyor.",
        "Redirect the upper-case variant to the lower-case URL with a 301.",
        "Büyük harfli varyantı küçük harfli URL'ye 301 ile yönlendirin.",
        "The upper-case URL redirects (301) or has a canonical to the lower-case URL.",
        "Büyük harfli URL 301 ile yönleniyor veya küçük harfli URL'ye canonical veriyor.",
        "Duplicate URL variants in repeated audits.",
        "Tekrarlanan denetimlerdeki yinelenen URL varyantları.",
    ),
    "index-file-duplicate": (
        "The home page is also reachable at /index.html or /index.php with a 200 and no canonical.",
        "Ana sayfa /index.html veya /index.php adresinden de 200 ile erişilebiliyor ve canonical yok.",
        "Redirect /index.html and /index.php to the root URL with a 301.",
        "/index.html ve /index.php adreslerini kök URL'ye 301 ile yönlendirin.",
        "The index-file URLs redirect (301) to the root or carry a canonical to it.",
        "index dosyası URL'leri köke 301 ile yönleniyor veya köke canonical veriyor.",
        "Duplicate home page URLs in repeated audits.",
        "Tekrarlanan denetimlerdeki yinelenen ana sayfa URL'leri.",
    ),
    "soft-404": (
        "A URL that does not exist answers with 200 (or redirects to a 200 page) instead of 404.",
        "Var olmayan bir URL 404 yerine 200 yanıtı veriyor (veya 200 veren bir sayfaya yönleniyor).",
        "Return a real 404 (or 410) status for missing pages; keep the friendly error page as the body.",
        "Olmayan sayfalar için gerçek 404 (veya 410) durum kodu döndürün; kullanıcıya dönük hata sayfası gövde olarak kalabilir.",
        "A request for a random non-existent path returns 404 or 410.",
        "Rastgele var olmayan bir yol istendiğinde 404 veya 410 dönüyor.",
        "Soft 404 entries in Search Console's page indexing report.",
        "Search Console sayfa dizinleme raporundaki 'Soft 404' kayıtları.",
    ),
    "no-custom-404": (
        "The 404 response looks like a bare server default page without navigation (heuristic).",
        "404 yanıtı gezinti içermeyen sade bir sunucu varsayılan sayfasına benziyor (sezgisel).",
        "Serve a branded 404 page with links to the home page and key sections.",
        "Ana sayfaya ve önemli bölümlere bağlantılar içeren, markaya uygun bir 404 sayfası sunun.",
        "The 404 page contains site navigation and links.",
        "404 sayfası site gezintisi ve bağlantılar içeriyor.",
        "Bounce rate on 404 pages in analytics.",
        "Analitikte 404 sayfalarındaki çıkış oranı.",
    ),
    "html-not-compressed": (
        "The HTML response is larger than 1.5 KB and is sent without compression (no Content-Encoding).",
        "HTML yanıtı 1,5 KB'dan büyük ve sıkıştırılmadan gönderiliyor (Content-Encoding yok).",
        "Enable Brotli or gzip compression for HTML, CSS and JavaScript on the server or CDN.",
        "Sunucuda veya CDN'de HTML, CSS ve JavaScript için Brotli veya gzip sıkıştırmasını açın.",
        "The HTML response carries Content-Encoding: br or gzip.",
        "HTML yanıtı Content-Encoding: br veya gzip içeriyor.",
        "Transfer size of the HTML document in the lab performance data.",
        "Lab performans verisinde HTML belgesinin aktarım boyutu.",
    ),
    "no-cache-validators": (
        "The HTML response has neither ETag nor Last-Modified, so clients cannot revalidate it cheaply (heuristic).",
        "HTML yanıtında ETag ve Last-Modified yok; istemciler ucuz yeniden doğrulama yapamaz (sezgisel).",
        "Send an ETag or Last-Modified header so repeat requests can be answered with 304.",
        "Tekrarlayan isteklere 304 verilebilmesi için ETag veya Last-Modified başlığı gönderin.",
        "The HTML response has an ETag or Last-Modified header.",
        "HTML yanıtında ETag veya Last-Modified başlığı var.",
        "Share of 304 responses in server logs.",
        "Sunucu günlüklerinde 304 yanıtlarının payı.",
    ),
    "server-version-disclosed": (
        "A response header reveals software and its version (Server or X-Powered-By).",
        "Bir yanıt başlığı yazılımı ve sürümünü açığa çıkarıyor (Server veya X-Powered-By).",
        "Remove the version from Server and drop X-Powered-By; this is hardening, not a ranking factor.",
        "Server başlığındaki sürümü kaldırın ve X-Powered-By'yi silin; bu bir sıkılaştırmadır, sıralama etkeni değildir.",
        "Server and X-Powered-By headers carry no version numbers.",
        "Server ve X-Powered-By başlıkları sürüm numarası taşımıyor.",
        "Security scanner reports on information disclosure.",
        "Güvenlik tarayıcılarının bilgi sızıntısı raporları.",
    ),
    "favicon-missing": (
        "No favicon is declared and /favicon.ico does not exist.",
        "Favicon tanımlı değil ve /favicon.ico mevcut değil.",
        'Add a favicon (a <link rel="icon"> or /favicon.ico); Google shows it next to mobile results.',
        'Bir favicon ekleyin (<link rel="icon"> veya /favicon.ico); Google bunu mobil sonuçlarda gösterir.',
        "The page declares an icon or /favicon.ico returns an image.",
        "Sayfa bir ikon tanımlıyor veya /favicon.ico bir görsel döndürüyor.",
        "Favicon shown next to the site in Google search results.",
        "Google arama sonuçlarında site yanında görünen favicon.",
    ),
    "manifest-invalid": (
        "The web app manifest linked from the page cannot be fetched or is not valid JSON.",
        "Sayfadan bağlanan web uygulaması manifesti alınamıyor veya geçerli JSON değil.",
        "Fix the manifest URL and make sure it is a valid JSON object (name, icons, start_url).",
        "Manifest URL'sini düzeltin ve geçerli bir JSON nesnesi olduğundan emin olun (name, icons, start_url).",
        "The manifest URL returns 200 with a JSON object.",
        "Manifest URL'si bir JSON nesnesiyle 200 dönüyor.",
        "Installability checks in browser developer tools.",
        "Tarayıcı geliştirici araçlarındaki kurulabilirlik kontrolleri.",
    ),
    "security-txt-missing": (
        "No /.well-known/security.txt with a Contact field was found.",
        "Contact alanı içeren bir /.well-known/security.txt bulunamadı.",
        "Publish /.well-known/security.txt (RFC 9116) so researchers know how to report vulnerabilities.",
        "Araştırmacıların açık bildirmesi için /.well-known/security.txt (RFC 9116) yayımlayın.",
        "/.well-known/security.txt returns 200 with a Contact field.",
        "/.well-known/security.txt, Contact alanıyla 200 dönüyor.",
        "Security reports received through the published contact.",
        "Yayımlanan iletişim üzerinden gelen güvenlik bildirimleri.",
    ),
}
_entries: dict[str, dict[str, str]] = {}
for _rid, (_a, _b, _c, _d, _e, _f, _g, _h) in _MSG.items():
    _entries[f"finding.{_rid}"] = {"en": _a, "tr": _b}
    _entries[f"rec.{_rid}"] = {"en": _c, "tr": _d}
    _entries[f"fail.{_rid}"] = {"en": _e, "tr": _f}
    _entries[f"lead.{_rid}"] = {"en": _g, "tr": _h}
register_messages(_entries)


# --------------------------------------------------------------------------- data
class RedirectVariant(BaseModel):
    name: str  # http | www-counterpart | trailing-slash | uppercase | index-html | index-php
    variant_url: str
    status: int | None = None  # status of the FIRST response
    final_url: str | None = None
    final_status: int | None = None
    hops: int = 0
    permanent: bool | None = None  # None when there was no redirect
    error: str | None = None


class Probe(BaseModel):
    url: str
    status: int | None = None
    present: bool = False
    detail: str | None = None
    error: str | None = None


class SiteSetup(BaseModel):
    redirects: list[RedirectVariant] = Field(default_factory=list)
    soft_404: dict[str, Any] = Field(default_factory=dict)
    custom_404: bool | None = None
    headers: dict[str, Any] = Field(default_factory=dict)
    hsts: dict[str, Any] = Field(default_factory=dict)
    http_version: str = "unknown"
    files: dict[str, Probe] = Field(default_factory=dict)
    requests_made: int = 0
    skipped: dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------- helpers
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_CANON = re.compile(r"<link\b[^>]*>", re.I)
_ATTR = re.compile(r"""([a-zA-Z-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_VERSION = re.compile(r"\d+\.\d+")


def _attrs(tag: str) -> dict[str, str]:
    return {m.group(1).lower(): (m.group(2) or m.group(3) or "") for m in _ATTR.finditer(tag)}


def _link_tags(html: str) -> list[dict[str, str]]:
    return [_attrs(m.group(0)) for m in _CANON.finditer(html[:300_000])]


def _title(html: str) -> str:
    m = _TITLE.search(html[:100_000])
    return re.sub(r"\s+", " ", m.group(1)).strip().lower() if m else ""


def _canonical(html: str, base: str) -> str | None:
    for a in _link_tags(html):
        if "canonical" in a.get("rel", "").lower().split() and a.get("href"):
            return urljoin(base, a["href"])
    return None


def _code(err: str | None) -> str | None:
    return err.partition(":")[0] if err else None


def _norm(url: str) -> str:
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc.lower(), p.path or "/", "", p.query, ""))


def _sibling(host: str) -> str | None:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return None
    except ValueError:
        pass
    if "." not in host:
        return None
    if host.startswith("www.") and host.count(".") >= 2:
        return host[4:]
    return f"www.{host}" if not host.startswith("www.") else None


def _variant(name: str, url: str, raw: RawResponse) -> RedirectVariant:
    chain = raw.redirect_chain or []
    return RedirectVariant(
        name=name,
        variant_url=url,
        status=chain[0].status if chain else raw.status,
        final_url=raw.final_url if raw.error is None else None,
        final_status=raw.status,
        hops=len(chain),
        permanent=(chain[0].status in (301, 308)) if chain else None,
        error=_code(raw.error),
    )


def _is_duplicate(raw: RawResponse, variant_url: str, base_title: str) -> bool:
    """200 on the variant itself, same title as the base page, and no canonical pointing elsewhere."""
    if raw.error or raw.status != 200 or raw.redirect_chain:
        return False
    html = decode_body(raw.body, raw.headers.get("content-type"))
    if not base_title or _title(html) != base_title:
        return False
    canon = _canonical(html, variant_url)
    return canon is None or _norm(canon) == _norm(variant_url)


def _hsts(headers: dict[str, str]) -> dict[str, Any]:
    v = headers.get("strict-transport-security")
    if not v:
        return {"present": False}
    age = re.search(r"max-age\s*=\s*(\d+)", v, re.I)
    low = v.lower()
    return {
        "present": True,
        "max_age": int(age.group(1)) if age else None,
        "include_subdomains": "includesubdomains" in low,
        "preload": "preload" in low,
    }


def _disclosure(headers: dict[str, str]) -> str | None:
    for key in ("server", "x-powered-by"):
        val = headers.get(key, "")
        if _VERSION.search(val) or (key == "x-powered-by" and val):
            return f"{key}: {val[:80]}"
    return None


def _same_host_page(inp: AnalysisInputs) -> tuple[str, str] | None:
    """(url, title) of a real page whose path is not the root, to test slash/case variants on."""
    host = urlparse(inp.origin).netloc.lower()
    cands: list[tuple[str, str]] = []
    ep = inp.entry_parsed
    cands.append((inp.entry_fetch.final_url or inp.entry_url, (ep.title if ep else "") or ""))
    for p in inp.pages:
        if p.status == 200 and p.parsed is not None and not p.error:
            cands.append((p.effective_url, p.parsed.title or ""))
    for url, title in cands:
        u = urlparse(url)
        last = u.path.rsplit("/", 1)[-1]
        if (
            u.netloc.lower() == host
            and u.path not in ("", "/")
            and not u.query
            and "." not in last
            and title.strip()
        ):
            return url, re.sub(r"\s+", " ", title).strip().lower()
    return None


class _Budget:
    def __init__(self, inp: AnalysisInputs) -> None:
        self.inp = inp
        self.used = 0

    async def get(self, url: str, max_bytes: int) -> RawResponse:
        if self.used >= MAX_REQUESTS:
            return RawResponse(url, url, None, {}, b"", False, "budget-exhausted")
        self.used += 1
        try:
            return await self.inp.fetcher.fetch_bytes(url, max_bytes=max_bytes)
        except Exception as exc:  # a fetcher bug must not kill the module
            return RawResponse(url, url, None, {}, b"", False, f"fetch-error: {type(exc).__name__}")


def _probe(url: str, raw: RawResponse, *, ok_if: bool, detail: str | None = None) -> Probe:
    return Probe(
        url=url,
        status=raw.status,
        present=ok_if and raw.error is None,
        detail=detail,
        error=_code(raw.error),
    )


# --------------------------------------------------------------------------- module
class SiteSetupModule:
    name = "site_setup"
    kind = "site_setup"
    timeout_s = 60.0

    async def run(self, inp: AnalysisInputs) -> ModuleResult:
        b = _Budget(inp)
        origin = inp.origin.rstrip("/")
        op = urlparse(origin)
        host = op.netloc
        out = SiteSetup()
        findings: list[Finding] = []
        not_checked: list[NotChecked] = []
        headers = inp.entry_fetch.headers
        html = inp.entry_html or inp.entry_fetch.html or ""

        # ---- plan the (at most 12) requests
        jobs: dict[str, tuple[str, int]] = {}  # key -> (url, max_bytes)
        if op.scheme == "https":
            jobs["http"] = (f"http://{host}/", _SMALL)
        sib = _sibling(op.hostname or "")
        if sib:
            port = f":{op.port}" if op.port else ""
            jobs["www-counterpart"] = (f"{op.scheme}://{sib}{port}/", _SMALL)
        page = _same_host_page(inp)
        if page:
            url, _t = page
            pu = urlparse(url)
            toggled = pu.path[:-1] if pu.path.endswith("/") else pu.path + "/"
            jobs["trailing-slash"] = (urlunparse(pu._replace(path=toggled)), _PAGE_BYTES)
            if pu.path.lower() != pu.path.upper():
                jobs["uppercase"] = (urlunparse(pu._replace(path=pu.path.upper())), _PAGE_BYTES)
        else:
            out.skipped["trailing-slash"] = out.skipped["uppercase"] = "no-non-root-page"
        jobs["index-html"] = (f"{origin}/index.html", _PAGE_BYTES)
        jobs["index-php"] = (f"{origin}/index.php", _PAGE_BYTES)
        probe_url = f"{origin}/{secrets.token_hex(12)}-seoa-probe"
        jobs["probe-404"] = (probe_url, 65_536)
        jobs["security"] = (f"{origin}/.well-known/security.txt", _SMALL)
        jobs["ads"] = (f"{origin}/ads.txt", _SMALL)
        jobs["humans"] = (f"{origin}/humans.txt", _SMALL)
        icon_declared = any(
            "icon" in a.get("rel", "").lower().split()
            or a.get("rel", "").lower() in ("shortcut icon", "apple-touch-icon")
            for a in _link_tags(html)
        )
        if not icon_declared:
            jobs["favicon"] = (f"{origin}/favicon.ico", _SMALL)
        manifest_href = next(
            (
                a["href"]
                for a in _link_tags(html)
                if "manifest" in a.get("rel", "").lower().split() and a.get("href")
            ),
            None,
        )
        if manifest_href:
            jobs["manifest"] = (
                urljoin(inp.entry_fetch.final_url or inp.entry_url, manifest_href),
                65_536,
            )

        keys = list(jobs)
        results = dict(
            zip(keys, await asyncio.gather(*(b.get(*jobs[k]) for k in keys)), strict=True)
        )

        # ---- redirect matrix
        for key in (
            "http",
            "www-counterpart",
            "trailing-slash",
            "uppercase",
            "index-html",
            "index-php",
        ):
            if key in results:
                out.redirects.append(_variant(key, jobs[key][0], results[key]))

        # ---- soft 404 / custom 404
        probe = results["probe-404"]
        soft = False
        if probe.error:
            not_checked.append(NotChecked(check_id="soft-404", reason_code="fetch-failed"))
            out.soft_404 = {"probe_url": probe_url, "error": _code(probe.error)}
        else:
            soft = probe.status == 200
            out.soft_404 = {
                "probe_url": probe_url,
                "status": (
                    probe.redirect_chain[0].status if probe.redirect_chain else probe.status
                ),
                "final_url": probe.final_url,
                "final_status": probe.status,
                "detected": soft,
            }
            if soft:
                ev = f"{probe_url} -> {probe.status}"
                if probe.redirect_chain:
                    ev += f" via redirect to {probe.final_url}"
                findings.append(make_finding("soft-404", url=origin, evidence=ev))
            elif probe.status in (404, 410):
                body = decode_body(probe.body, probe.headers.get("content-type"))
                bare = len(probe.body) < 600 or "<a " not in body.lower()
                out.custom_404 = not bare
                if bare:
                    findings.append(
                        make_finding(
                            "no-custom-404",
                            url=origin,
                            evidence=f"{probe.status}, {len(probe.body)} bytes, no links",
                            confidence="medium",
                        )
                    )

        # ---- duplicate URL variants (a soft-404 site answers 200 to everything: skip them)
        if soft:
            for cid in (
                "trailing-slash-duplicate",
                "uppercase-path-duplicate",
                "index-file-duplicate",
            ):
                not_checked.append(NotChecked(check_id=cid, reason_code="soft-404-site"))
        else:
            if page:
                for key, cid in (
                    ("trailing-slash", "trailing-slash-duplicate"),
                    ("uppercase", "uppercase-path-duplicate"),
                ):
                    if key in results and _is_duplicate(results[key], jobs[key][0], page[1]):
                        findings.append(
                            make_finding(cid, url=jobs[key][0], evidence=f"{jobs[key][0]} -> 200")
                        )
            home_title = _title(html) or (
                inp.entry_parsed.title.strip().lower() if inp.entry_parsed else ""
            )
            idx = [
                k
                for k in ("index-html", "index-php")
                if _is_duplicate(results[k], jobs[k][0], home_title)
            ]
            if idx:
                findings.append(
                    make_finding(
                        "index-file-duplicate",
                        url=jobs[idx[0]][0],
                        evidence=", ".join(jobs[k][0] for k in idx),
                    )
                )

        # ---- entry page headers
        enc = headers.get("content-encoding", "").lower()
        ctype = (headers.get("content-type") or inp.entry_fetch.content_type or "").lower()
        out.headers = {
            "content_encoding": enc or None,
            "cache_control": headers.get("cache-control"),
            "etag": "etag" in headers,
            "last_modified": "last-modified" in headers,
            "vary": headers.get("vary"),
            "server": headers.get("server"),
            "x_powered_by": headers.get("x-powered-by"),
        }
        out.hsts = _hsts(headers) if op.scheme == "https" else {}
        if inp.entry_fetch.status == 200 and "html" in ctype:
            if not enc and inp.entry_fetch.html_bytes > 1536:
                findings.append(
                    make_finding(
                        "html-not-compressed",
                        url=inp.entry_url,
                        evidence=f"{inp.entry_fetch.html_bytes} bytes, no Content-Encoding",
                    )
                )
            if "etag" not in headers and "last-modified" not in headers:
                findings.append(
                    make_finding(
                        "no-cache-validators",
                        url=inp.entry_url,
                        evidence="no ETag, no Last-Modified",
                        confidence="medium",
                    )
                )
        if (disc := _disclosure(headers)) is not None:
            findings.append(
                make_finding("server-version-disclosed", url=inp.entry_url, evidence=disc)
            )

        # ---- well-known files
        sec = results["security"]
        sec_text = (
            decode_body(sec.body, sec.headers.get("content-type")) if sec.status == 200 else ""
        )
        has_contact = bool(re.search(r"^\s*contact\s*:", sec_text, re.I | re.M))
        out.files["security_txt"] = _probe(
            jobs["security"][0], sec, ok_if=sec.status == 200 and has_contact
        )
        if not (sec.error is None and sec.status == 200 and has_contact):
            if sec.error:
                not_checked.append(
                    NotChecked(check_id="security-txt-missing", reason_code="fetch-failed")
                )
            else:
                findings.append(
                    make_finding(
                        "security-txt-missing",
                        url=origin,
                        evidence=f"{jobs['security'][0]} -> {sec.status}",
                    )
                )
        for key, name in (("ads", "ads_txt"), ("humans", "humans_txt")):
            r = results[key]
            is_text = r.status == 200 and "html" not in r.headers.get("content-type", "").lower()
            out.files[name] = _probe(jobs[key][0], r, ok_if=is_text)

        if icon_declared:
            out.files["favicon"] = Probe(url=origin, present=True, detail="declared in HTML")
        else:
            fv = results["favicon"]
            has_icon = (
                fv.status == 200
                and bool(fv.body)
                and "html" not in fv.headers.get("content-type", "").lower()
            )
            out.files["favicon"] = _probe(jobs["favicon"][0], fv, ok_if=has_icon)
            if fv.error:
                not_checked.append(
                    NotChecked(check_id="favicon-missing", reason_code="fetch-failed")
                )
            elif not has_icon:
                findings.append(
                    make_finding(
                        "favicon-missing",
                        url=origin,
                        evidence=f"{jobs['favicon'][0]} -> {fv.status}",
                    )
                )

        if "manifest" in results:
            mr = results["manifest"]
            detail = None
            valid = False
            if mr.error is None and mr.status == 200:
                try:
                    doc = json.loads(decode_body(mr.body, mr.headers.get("content-type")))
                    valid = isinstance(doc, dict)
                    detail = "ok" if valid else "not a JSON object"
                except ValueError:
                    detail = "invalid JSON"
            else:
                detail = f"status {mr.status}" if mr.error is None else _code(mr.error)
            out.files["manifest"] = _probe(jobs["manifest"][0], mr, ok_if=valid, detail=detail)
            if not valid and mr.error is None:
                findings.append(
                    make_finding("manifest-invalid", url=jobs["manifest"][0], evidence=detail)
                )

        out.requests_made = b.used
        return ModuleResult(kind=self.kind, data=out, findings=findings, not_checked=not_checked)


register_module(SiteSetupModule())
