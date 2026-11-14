"""Local SEO / NAP module (belge 12 C4): name, address, phone from the sampled pages.

Pure and offline: it reads what the audit already fetched. Sources, in order of trust:
JSON-LD (``LocalBusiness`` and friends, ``Organization`` with address/telephone), ``tel:`` links,
and phone / address patterns in the visible text. Text patterns are HEURISTIC: a number or street
line found in prose is a candidate, not a fact (a Turkish national number needs the leading ``0``
and ten digits, an international one a ``+``; an address line needs a street word and a number).
Nothing is guessed when a pattern does not fit.

What counts as an inconsistency (a different NUMBER or ADDRESS, never a different spelling of the
same one - numbers are compared on their last ten digits, addresses folded for case and
punctuation):
* the JSON-LD telephone of a page is not among the phones shown on that page,
* the JSON-LD telephones of different pages differ,
* the JSON-LD addresses of different pages differ.
A site may legitimately show several phones; that alone is not reported.

No local-business signal (no LocalBusiness-type markup and no phone + address pair, no map embed
with either) -> ``NotChecked("local", "not-applicable")`` and no finding.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from seoa.application.analysis.links.duplicates import fold
from seoa.application.analysis.plugin import AnalysisInputs, ModuleResult, register_module
from seoa.application.analysis.types import AnalysisPage
from seoa.domain import Category, Finding, NotChecked, Severity
from seoa.domain.rules.registry import CheckDef, make_finding, register, register_messages

MAX_PAGES = 60
MAX_TEXT = 200_000
MAX_HTML = 1_500_000
MAX_NODES = 400
MAX_DEPTH = 6
LIST_CAP = 20
MIN_DIGITS = 7

LOCAL_TYPES = frozenset(
    {
        "LocalBusiness",
        "Restaurant",
        "Store",
        "Dentist",
        "Physician",
        "MedicalClinic",
        "MedicalBusiness",
        "Hospital",
        "Pharmacy",
        "LegalService",
        "Attorney",
        "Notary",
        "RealEstateAgent",
        "AutoRepair",
        "AutoDealer",
        "AutomotiveBusiness",
        "BeautySalon",
        "HairSalon",
        "DaySpa",
        "HealthAndBeautyBusiness",
        "Hotel",
        "LodgingBusiness",
        "FoodEstablishment",
        "CafeOrCoffeeShop",
        "Bakery",
        "BarOrPub",
        "GroceryStore",
        "HealthClub",
        "GymOrFitnessCenter",
        "SportsActivityLocation",
        "FinancialService",
        "AccountingService",
        "InsuranceAgency",
        "HomeAndConstructionBusiness",
        "Electrician",
        "Plumber",
        "Locksmith",
        "ProfessionalService",
        "TravelAgency",
        "ChildCare",
        "EntertainmentBusiness",
        "ShoppingCenter",
        "ClothingStore",
        "FurnitureStore",
        "ElectronicsStore",
        "Florist",
        "Library",
        "School",
        "VeterinaryCare",
        "PetStore",
    }
)

# --------------------------------------------------------------------------- rules

_RULES: tuple[tuple[str, Severity], ...] = (
    ("local-nap-inconsistent", Severity.MEDIUM),
    ("local-no-phone-link", Severity.LOW),
)
for _id, _sev in _RULES:
    register(
        CheckDef(
            id=_id,
            category=Category.ONPAGE,
            severity=_sev,
            scope="site",
            heuristic=True,
            effort_default="S",
            impact_default="low" if _sev is Severity.LOW else "medium",
            message_key=f"finding.{_id}",
            recommendation_key=f"rec.{_id}",
            failure_check_key=f"fail.{_id}",
            leading_indicator_key=f"lead.{_id}",
        )
    )
LOCAL_RULE_IDS = tuple(r[0] for r in _RULES)

_MSG: dict[str, tuple[str, str, str, str, str, str, str, str]] = {
    "local-nap-inconsistent": (
        "The business name, address or phone number is not the same everywhere on the site "
        "(a different number or address, not just a different spelling).",
        "İşletme adı, adresi veya telefonu sitenin her yerinde aynı değil "
        "(yazım farkı değil, farklı bir numara veya adres).",
        "Pick one canonical phone number and address, and use it in the structured data, the "
        "visible text and the footer of every page.",
        "Tek bir resmî telefon ve adres belirleyin; yapılandırılmış veride, görünen metinde ve her "
        "sayfanın alt bölümünde aynısını kullanın.",
        "The structured-data phone and address equal the ones shown on the page, on every page.",
        "Yapılandırılmış veri telefonu ve adresi, her sayfada görünenlerle aynı.",
        "Consistency of the business details across your profiles and directories.",
        "İşletme bilgilerinin profilleriniz ve dizinlerdeki tutarlılığı.",
    ),
    "local-no-phone-link": (
        "A phone number is shown as plain text but no link starts the call on a phone "
        "(no tel: link).",
        "Telefon numarası düz metin olarak gösteriliyor ancak telefonda aramayı başlatan bir "
        "bağlantı (tel:) yok.",
        'Wrap the phone number in a link such as <a href="tel:+90...">, using the international '
        "format.",
        'Telefon numarasını uluslararası biçimde <a href="tel:+90..."> gibi bir bağlantıya alın.',
        "The phone number is a tel: link on the pages that show it.",
        "Telefon numarası, gösterildiği sayfalarda tel: bağlantısı.",
        "Taps on the phone number in the mobile report of your analytics.",
        "Analitik raporunuzdaki mobil telefon numarası dokunmaları.",
    ),
}
register_messages(
    {
        key: {"en": en, "tr": tr}
        for rid, m in _MSG.items()
        for key, en, tr in (
            (f"finding.{rid}", m[0], m[1]),
            (f"rec.{rid}", m[2], m[3]),
            (f"fail.{rid}", m[4], m[5]),
            (f"lead.{rid}", m[6], m[7]),
        )
    }
)


# --------------------------------------------------------------------------- output model


class PhoneEntry(BaseModel):
    number: str  # normalised (+90..., +49..., digits when the country is unknown)
    formats: list[str] = Field(default_factory=list)  # how it is written (raw spellings)
    pages: list[str] = Field(default_factory=list)
    sources: list[Literal["schema", "tel-link", "text"]] = Field(default_factory=list)


class AddressEntry(BaseModel):
    text: str
    source: Literal["schema", "text"]  # "text" is a heuristic candidate
    pages: list[str] = Field(default_factory=list)


class NapInconsistency(BaseModel):
    kind: Literal["phone", "address"]
    code: Literal["schema-phone-not-on-page", "schema-phones-differ", "schema-addresses-differ"]
    values: list[str] = Field(default_factory=list)
    pages: list[str] = Field(default_factory=list)


class LocalSeo(BaseModel):
    applicable: bool = False
    signals: list[str] = Field(default_factory=list)  # stable codes the report translates
    business_types: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    phones: list[PhoneEntry] = Field(default_factory=list)
    addresses: list[AddressEntry] = Field(default_factory=list)
    inconsistencies: list[NapInconsistency] = Field(default_factory=list)
    has_tel_link: bool = False
    has_map_embed: bool = False
    pages_scanned: int = 0
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- extraction

_INTL = re.compile(r"(?<![\w+])\+\d{1,3}[ .\-]?\(?\d{1,4}\)?(?:[ .\-]?\d{2,4}){2,4}(?!\d)")
_TR = re.compile(
    r"(?<![\w+])0[ ]?\(?[2-5]\d{2}\)?[ .\-]?\d{3}[ .\-]?\d{2}[ .\-]?\d{2}(?!\d)",
)
_STREET_TR = re.compile(
    r"[^\n]{0,60}?\b(?:Mah\.?|Mahallesi|Cad\.?|Caddesi|Sok\.?|Sokak|Sk\.|Bulvar[ıi]|Blv\.)"
    r"[^\n]{0,100}",
    re.IGNORECASE,
)
_STREET_EN = re.compile(
    r"\b\d{1,5}[ ]+[A-Z][A-Za-z.]{1,20}(?:[ ]+[A-Z][A-Za-z.]{1,20}){0,3}[ ]+"
    r"(?:Street|St\.|Avenue|Ave\.|Road|Rd\.|Boulevard|Blvd\.|Lane|Drive)\b[^\n]{0,60}"
)
_HAS_NUMBER = re.compile(r"\d")
_MAP_EMBED = re.compile(
    r"<iframe\b[^>]{0,800}?\bsrc\s*=\s*[\"'][^\"']{0,400}?"
    r"(?:google\.[a-z.]{2,6}/maps|maps\.google\.|openstreetmap\.org/export)",
    re.IGNORECASE,
)


def phone_key(number: str) -> str:
    """Comparison key: the last ten digits (national significant number, close enough)."""
    return re.sub(r"\D", "", number)[-10:]


def normalise_phone(raw: str) -> str | None:
    """+90... for Turkish national numbers, +digits for international ones, digits otherwise."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) < MIN_DIGITS or len(digits) > 15:
        return None
    s = raw.strip()
    if s.startswith("+"):
        return "+" + digits
    if digits.startswith("00"):
        return "+" + digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        return "+90" + digits[1:]
    if digits.startswith("90") and len(digits) == 12:
        return "+" + digits
    return digits


def text_phones(text: str) -> list[tuple[str, str]]:
    """(normalised, raw) pairs found in prose; only well-formed Turkish or +international shapes."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for rx in (_TR, _INTL):
        for m in rx.finditer(text[:MAX_TEXT]):
            raw = m.group(0).strip()
            norm = normalise_phone(raw)
            if norm is None or phone_key(norm) in seen:
                continue
            seen.add(phone_key(norm))
            out.append((norm, raw))
            if len(out) >= LIST_CAP:
                return out
    return out


def text_addresses(text: str) -> list[str]:
    out: list[str] = []
    for rx in (_STREET_TR, _STREET_EN):
        for m in rx.finditer(text[:MAX_TEXT]):
            line = re.sub(r"\s+", " ", m.group(0)).strip(" ,;-")
            if _HAS_NUMBER.search(line) and 12 <= len(line) <= 200 and line not in out:
                out.append(line)
            if len(out) >= LIST_CAP:
                return out
    return out


def address_key(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", fold(text))


def _as_list(v: Any) -> list[Any]:
    return v if isinstance(v, list) else [v]


def _addr_text(v: Any) -> str:
    if isinstance(v, str):
        return re.sub(r"\s+", " ", v).strip()
    if isinstance(v, dict):
        parts = [
            str(v.get(k, "")).strip()
            for k in ("streetAddress", "postalCode", "addressLocality", "addressRegion")
            if isinstance(v.get(k), str | int)
        ]
        return ", ".join(p for p in parts if p)
    return ""


class _Schema:
    def __init__(self) -> None:
        self.types: set[str] = set()
        self.names: list[str] = []
        self.phones: list[str] = []
        self.addresses: list[str] = []


def schema_nap(page: AnalysisPage) -> _Schema:
    """Business types, names, telephones and addresses of one page's JSON-LD (bounded walk)."""
    out = _Schema()
    if page.parsed is None:
        return out
    budget = [MAX_NODES]

    def walk(node: Any, depth: int) -> None:
        if budget[0] <= 0 or depth > MAX_DEPTH:
            return
        budget[0] -= 1
        if isinstance(node, list):
            for x in node[:50]:
                walk(x, depth + 1)
            return
        if not isinstance(node, dict):
            return
        types = {t for t in _as_list(node.get("@type", [])) if isinstance(t, str)}
        local = bool(types & LOCAL_TYPES)
        if local:
            out.types |= types & LOCAL_TYPES
        if local or types & {"Organization", "Corporation", "OnlineBusiness"}:
            name = node.get("name")
            if isinstance(name, str) and name.strip():
                out.names.append(name.strip()[:120])
            for tel in _as_list(node.get("telephone", [])):
                if isinstance(tel, str | int) and str(tel).strip():
                    out.phones.append(str(tel).strip())
            for addr in _as_list(node.get("address", [])):
                text = _addr_text(addr)
                if text:
                    out.addresses.append(text[:200])
        for key, val in node.items():
            if key in ("@graph", "mainEntity", "department", "location", "provider", "publisher"):
                walk(val, depth + 1)

    for block in page.parsed.jsonld:
        walk(block.data, 0)
    return out


def _tel_links(page: AnalysisPage) -> list[str]:
    if page.parsed is None:
        return []
    out = []
    for link in page.parsed.links:
        if link.href.strip().lower().startswith("tel:"):
            raw = link.href.strip()[4:].split(";")[0].strip()
            if raw:
                out.append(raw)
    return out


def _add_unique(items: list[str], value: str, cap: int) -> None:
    if value not in items and len(items) < cap:
        items.append(value)


# --------------------------------------------------------------------------- analysis


def analyse(pages: list[AnalysisPage], entry_html: str, entry_url: str) -> LocalSeo:
    rep = LocalSeo()
    sample = [p for p in pages if p.parsed is not None and (p.status or 0) < 400 and not p.error]
    sample = sample[:MAX_PAGES]
    rep.pages_scanned = len(sample)
    rep.has_map_embed = bool(_MAP_EMBED.search(entry_html[:MAX_HTML])) if entry_html else False

    phones: dict[str, PhoneEntry] = {}
    addresses: dict[tuple[str, str], AddressEntry] = {}
    schema_phone_by_page: dict[str, set[str]] = {}
    schema_phone_values: dict[str, str] = {}  # key -> normalised
    schema_phone_pages: dict[str, list[str]] = {}
    schema_addr_values: dict[str, str] = {}
    schema_addr_pages: dict[str, list[str]] = {}
    shown_by_page: dict[str, set[str]] = {}

    def add_phone(
        norm: str, raw: str, url: str, source: Literal["schema", "tel-link", "text"]
    ) -> None:
        e = phones.setdefault(phone_key(norm), PhoneEntry(number=norm))
        if raw not in e.formats and len(e.formats) < 6:
            e.formats.append(raw[:40])
        _add_unique(e.pages, url, 10)
        if source not in e.sources:
            e.sources.append(source)

    for p in sample:
        url = p.effective_url
        sc = schema_nap(p)
        rep.business_types = sorted(set(rep.business_types) | sc.types)
        for n in sc.names:
            _add_unique(rep.names, n, 5)
        shown = shown_by_page.setdefault(url, set())
        for raw in sc.phones:
            norm = normalise_phone(raw)
            if norm is None:
                continue
            add_phone(norm, raw, url, "schema")
            schema_phone_by_page.setdefault(url, set()).add(phone_key(norm))
            schema_phone_values.setdefault(phone_key(norm), norm)
            _add_unique(schema_phone_pages.setdefault(phone_key(norm), []), url, 10)
        for raw in _tel_links(p):
            norm = normalise_phone(raw)
            if norm is None:
                continue
            rep.has_tel_link = True
            add_phone(norm, raw, url, "tel-link")
            shown.add(phone_key(norm))
        text = p.parsed.visible_text if p.parsed else ""
        for norm, raw in text_phones(text):
            add_phone(norm, raw, url, "text")
            shown.add(phone_key(norm))
        for a in sc.addresses:
            k = address_key(a)
            if not k:
                continue
            ent = addresses.setdefault((k, "schema"), AddressEntry(text=a, source="schema"))
            _add_unique(ent.pages, url, 10)
            schema_addr_values.setdefault(k, a)
            _add_unique(schema_addr_pages.setdefault(k, []), url, 10)
        for a in text_addresses(text):
            k = address_key(a)
            if not k or any(k in sk or sk in k for sk, _src in addresses if _src == "schema"):
                continue  # already known from structured data
            ent = addresses.setdefault((k, "text"), AddressEntry(text=a, source="text"))
            _add_unique(ent.pages, url, 10)

    rep.phones = list(phones.values())[:LIST_CAP]
    rep.addresses = list(addresses.values())[:LIST_CAP]

    # inconsistencies: different numbers / addresses, never different spellings
    for url, keys in schema_phone_by_page.items():
        shown = shown_by_page.get(url, set())
        if shown and not (keys & shown):
            rep.inconsistencies.append(
                NapInconsistency(
                    kind="phone",
                    code="schema-phone-not-on-page",
                    values=[schema_phone_values[k] for k in sorted(keys)][:4],
                    pages=[url],
                )
            )
    if len(schema_phone_values) > 1:
        rep.inconsistencies.append(
            NapInconsistency(
                kind="phone",
                code="schema-phones-differ",
                values=[schema_phone_values[k] for k in sorted(schema_phone_values)][:6],
                pages=[u for k in sorted(schema_phone_pages) for u in schema_phone_pages[k]][:6],
            )
        )
    if len(schema_addr_values) > 1:
        rep.inconsistencies.append(
            NapInconsistency(
                kind="address",
                code="schema-addresses-differ",
                values=[schema_addr_values[k] for k in sorted(schema_addr_values)][:4],
                pages=[u for k in sorted(schema_addr_pages) for u in schema_addr_pages[k]][:6],
            )
        )

    has_text_phone = any("text" in e.sources for e in phones.values())
    has_phone = bool(phones)
    has_addr = bool(addresses)
    if rep.business_types:
        rep.signals.append("schema-local-business")
    if has_phone and has_addr:
        rep.signals.append("phone-and-address")
    if rep.has_map_embed and (has_phone or has_addr):
        rep.signals.append("map-embed")
    if rep.has_tel_link:
        rep.signals.append("tel-link")
    if has_text_phone and not rep.has_tel_link:
        rep.notes.append("phone-without-tel-link")
    if any(e.source == "text" for e in addresses.values()):
        rep.notes.append("address-from-text-is-heuristic")
    rep.applicable = bool(
        rep.business_types
        or (has_phone and has_addr)
        or (rep.has_map_embed and (has_phone or has_addr))
    )
    return rep


def audit_local(inp: AnalysisInputs) -> tuple[LocalSeo, list[Finding], list[NotChecked]]:
    rep = analyse(inp.pages, inp.entry_html, inp.entry_url)
    findings: list[Finding] = []
    nc: list[NotChecked] = []
    if not rep.applicable:
        nc.append(NotChecked(check_id="local", reason_code="not-applicable"))
        nc += [NotChecked(check_id=rid, reason_code="not-applicable") for rid in LOCAL_RULE_IDS]
        return rep, findings, nc
    for inc in rep.inconsistencies[:5]:
        findings.append(
            make_finding(
                "local-nap-inconsistent",
                url=inc.pages[0] if inc.pages else None,
                evidence=f"{inc.code}: {' | '.join(inc.values)}",
                confidence="medium",
            )
        )
    text_phone = next((e for e in rep.phones if "text" in e.sources), None)
    if text_phone is not None and not rep.has_tel_link:
        findings.append(
            make_finding(
                "local-no-phone-link",
                url=text_phone.pages[0] if text_phone.pages else inp.entry_url,
                evidence=text_phone.formats[0] if text_phone.formats else text_phone.number,
                confidence="medium",
            )
        )
    elif not rep.phones:
        nc.append(NotChecked(check_id="local-no-phone-link", reason_code="no-phone-found"))
    return rep, findings, nc


class LocalModule:
    name = "local"
    kind = "local"
    timeout_s = 30.0

    async def run(self, inp: AnalysisInputs) -> ModuleResult:
        rep, findings, nc = audit_local(inp)
        return ModuleResult(kind=self.kind, data=rep, findings=findings, not_checked=nc)


register_module(LocalModule())

__all__ = [
    "LOCAL_RULE_IDS",
    "LocalModule",
    "LocalSeo",
    "analyse",
    "audit_local",
    "normalise_phone",
    "phone_key",
    "text_addresses",
    "text_phones",
]
