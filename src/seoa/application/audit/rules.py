"""Rules produced by the pipeline itself (status codes, duplicates, JS dependence, https)."""

from __future__ import annotations

from seoa.domain import Category, Layer, Severity
from seoa.domain.rules.registry import CheckDef, register, register_messages

T, ON = Category.TECHNICAL, Category.ONPAGE

_DEFS = [
    CheckDef(
        "schema-none-found",
        Category.SCHEMA,
        Severity.INFO,
        heuristic=True,
        effort_default="M",
        impact_default="low",
    ),
    CheckDef("page-status-4xx", T, Severity.MEDIUM, effort_default="M", impact_default="medium"),
    CheckDef("page-status-5xx", T, Severity.HIGH, effort_default="M", impact_default="high"),
    CheckDef(
        "redirect-chain-long",
        T,
        Severity.LOW,
        heuristic=True,
        effort_default="S",
        impact_default="low",
    ),
    CheckDef(
        "https-unavailable",
        T,
        Severity.HIGH,
        scope="site",
        effort_default="M",
        impact_default="high",
    ),
    CheckDef(
        "slow-ttfb", T, Severity.LOW, heuristic=True, effort_default="M", impact_default="medium"
    ),
    CheckDef(
        "duplicate-title",
        ON,
        Severity.MEDIUM,
        scope="page",
        effort_default="S",
        impact_default="medium",
    ),
    CheckDef(
        "duplicate-meta-description",
        ON,
        Severity.LOW,
        scope="page",
        effort_default="S",
        impact_default="low",
    ),
    CheckDef(
        "js-dependent-content",
        Category.AI_READINESS,
        Severity.MEDIUM,
        heuristic=True,
        effort_default="L",
        impact_default="high",
    ),
]
for d in _DEFS:
    register(d)

register_messages(
    {
        "finding.page-status-4xx": {
            "en": "A sampled page answers with a 4xx status (not found or blocked).",
            "tr": "Örneklenen bir sayfa 4xx durum kodu döndürüyor (bulunamadı veya engelli).",
        },
        "finding.page-status-5xx": {
            "en": "A sampled page answers with a 5xx server error.",
            "tr": "Örneklenen bir sayfa 5xx sunucu hatası döndürüyor.",
        },
        "finding.redirect-chain-long": {
            "en": "The URL redirects through two or more hops before the final page. This is a heuristic, not a search engine limit.",
            "tr": "URL, son sayfaya ulaşmadan önce iki veya daha fazla yönlendirmeden geçiyor. Bu bir sezgidir, arama motoru sınırı değildir.",
        },
        "finding.https-unavailable": {
            "en": "The site could not be reached over HTTPS but answers over plain HTTP.",
            "tr": "Siteye HTTPS üzerinden ulaşılamadı, ancak düz HTTP üzerinden yanıt veriyor.",
        },
        "finding.slow-ttfb": {
            "en": "The server took more than 1.8 seconds to start answering from this measurement point. The figure depends on where it was measured; it is a heuristic.",
            "tr": "Sunucu bu ölçüm noktasından yanıt vermeye 1,8 saniyeden uzun sürede başladı. Değer ölçüm yerine bağlıdır; bir sezgidir.",
        },
        "finding.duplicate-title": {
            "en": "Several sampled pages share the same title tag.",
            "tr": "Örneklenen birden çok sayfa aynı title etiketini kullanıyor.",
        },
        "finding.duplicate-meta-description": {
            "en": "Several sampled pages share the same meta description.",
            "tr": "Örneklenen birden çok sayfa aynı meta açıklamasını kullanıyor.",
        },
        "finding.js-dependent-content": {
            "en": "A large share of the page content only exists after JavaScript runs. Many AI crawlers do not run JavaScript (heuristic).",
            "tr": "Sayfa içeriğinin büyük bölümü yalnızca JavaScript çalıştıktan sonra oluşuyor. Birçok yapay zekâ tarayıcısı JavaScript çalıştırmaz (sezgisel).",
        },
        "rec.page-status-4xx": {
            "en": "Fix or redirect the broken URL, and remove internal links that point to it.",
            "tr": "Bozuk URL'yi düzeltin veya yönlendirin, ona giden iç bağlantıları kaldırın.",
        },
        "rec.page-status-5xx": {
            "en": "Investigate the server error; a page that fails to load cannot be indexed.",
            "tr": "Sunucu hatasını inceleyin; yüklenmeyen sayfa indekslenemez.",
        },
        "rec.redirect-chain-long": {
            "en": "Link directly to the final URL and redirect in a single step (301/308).",
            "tr": "Doğrudan son URL'ye bağlantı verin ve tek adımda yönlendirin (301/308).",
        },
        "rec.https-unavailable": {
            "en": "Install a valid TLS certificate and serve the site over HTTPS, then redirect HTTP to HTTPS.",
            "tr": "Geçerli bir TLS sertifikası kurup siteyi HTTPS üzerinden sunun, HTTP'yi HTTPS'e yönlendirin.",
        },
        "rec.slow-ttfb": {
            "en": "Check server response time, caching and hosting; compare with field data before acting.",
            "tr": "Sunucu yanıt süresini, önbelleği ve barındırmayı kontrol edin; harekete geçmeden önce saha verisiyle karşılaştırın.",
        },
        "rec.duplicate-title": {
            "en": "Give every page a unique title that names what the page is about.",
            "tr": "Her sayfaya konusunu anlatan benzersiz bir title verin.",
        },
        "rec.duplicate-meta-description": {
            "en": "Write a distinct description for each page, or leave it out so the engine writes one.",
            "tr": "Her sayfa için ayrı bir açıklama yazın veya arama motorunun yazması için boş bırakın.",
        },
        "rec.js-dependent-content": {
            "en": "Serve the main content in the initial HTML (server-side rendering or pre-rendering).",
            "tr": "Ana içeriği ilk HTML'de sunun (sunucu tarafı render veya ön render).",
        },
        **{
            f"fail.{d.id}": {
                "en": "Re-run the audit: the finding should no longer appear.",
                "tr": "Denetimi yeniden çalıştırın: bulgu artık görünmemeli.",
            }
            for d in _DEFS
        },
        **{
            f"lead.{d.id}": {
                "en": "Watch this finding's count over repeated audits.",
                "tr": "Tekrarlanan denetimlerde bu bulgunun sayısını izleyin.",
            }
            for d in _DEFS
        },
    }
)
assert all(d.layer == Layer.A for d in _DEFS)
