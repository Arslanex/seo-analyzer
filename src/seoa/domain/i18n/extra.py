"""TR + EN strings for local SEO, the suggested sitemap and authority (belge 12 C4/C5/B2)."""

from __future__ import annotations

# (key, tr, en)
ENTRIES: list[tuple[str, str, str]] = [
    ("sec.local", "Yerel SEO", "Local SEO"),
    ("sec.sitemapgen", "Sitemap önerisi", "Suggested sitemap"),
    ("sec.authority", "Alan adı otoritesi", "Domain authority"),
    # --- reasons
    (
        "reason.site-mode-only",
        "Sitemap önerisi yalnız site denetiminde üretilir (tek sayfa denetiminde örneklem yok).",
        "The suggested sitemap is built only in site audits (a single-page audit has no sample).",
    ),
    (
        "reason.no-eligible-pages",
        "Örneklemde sitemap'e uygun (200, noindex olmayan, kendine canonical) sayfa yok.",
        "No page in the sample qualifies for a sitemap (200, not noindex, self-canonical).",
    ),
    (
        "reason.no-api-key",
        "OpenPageRank anahtarı tanımlı değil. Ücretsiz anahtarı keywordseverywhere.com/account/openpagerank adresinden alıp .env içine SEOA_OPENPAGERANK_KEY olarak ekleyin.",
        "No OpenPageRank key is set. Get a free key at keywordseverywhere.com/account/openpagerank and add it to .env as SEOA_OPENPAGERANK_KEY.",
    ),
    (
        "reason.authority-no-data",
        "OpenPageRank bu alan adı için veri döndürmedi.",
        "OpenPageRank returned no data for this domain.",
    ),
    (
        "reason.authority-unauthorized",
        "OpenPageRank anahtarı reddedildi. Eski openpagerank.com anahtarları artık çalışmıyor; keywordseverywhere.com/account/openpagerank adresinden yenisini alın. Ücretsiz anahtar tek bir IP adresine bağlıdır.",
        "The OpenPageRank key was rejected. Keys from the old openpagerank.com no longer work; create a new one at keywordseverywhere.com/account/openpagerank. A free key is tied to one IP address.",
    ),
    (
        "reason.authority-rate-limited",
        "OpenPageRank istek sınırına ulaşıldı.",
        "The OpenPageRank rate limit was reached.",
    ),
    ("reason.authority-timeout", "OpenPageRank zaman aşımına uğradı.", "OpenPageRank timed out."),
    (
        "reason.authority-unreachable",
        "OpenPageRank'e ulaşılamadı.",
        "OpenPageRank could not be reached.",
    ),
    (
        "reason.authority-target-rejected",
        "OpenPageRank adresi güvenlik politikası nedeniyle reddedildi.",
        "The OpenPageRank address was rejected by the safety policy.",
    ),
    (
        "reason.authority-too-large",
        "OpenPageRank yanıtı çok büyük.",
        "The OpenPageRank response was too large.",
    ),
    (
        "reason.authority-bad-json",
        "OpenPageRank yanıtı okunamadı.",
        "The OpenPageRank response could not be read.",
    ),
    # --- local
    (
        "local.intro",
        "İşletme adı, adres ve telefon (NAP) sayfalardaki yapılandırılmış veriden, tel: bağlantılarından ve görünen metinden çıkarılır. Metinden çıkarılanlar sezgiseldir (aday, kesin bilgi değil). Tutarsızlık = farklı numara/adres; aynı numaranın farklı yazılışı tutarsızlık sayılmaz.",
        "Business name, address and phone (NAP) are taken from the structured data, tel: links and visible text of the pages. What comes from text is heuristic (a candidate, not a fact). An inconsistency means a different number or address; a different spelling of the same number is not one.",
    ),
    ("local.fact.pages", "Taranan sayfa", "Pages scanned"),
    ("local.fact.tel", "tel: bağlantısı var", "tel: link present"),
    ("local.fact.map", "Gömülü harita var (giriş sayfası)", "Embedded map (entry page)"),
    ("local.fact.types", "İşletme türleri (schema)", "Business types (schema)"),
    ("local.fact.names", "Adlar (schema)", "Names (schema)"),
    ("local.fact.signals", "Yerel işletme sinyalleri", "Local-business signals"),
    ("local.signal.schema-local-business", "LocalBusiness işaretlemesi", "LocalBusiness markup"),
    ("local.signal.phone-and-address", "telefon ve adres birlikte", "phone and address together"),
    ("local.signal.map-embed", "gömülü harita", "embedded map"),
    ("local.signal.tel-link", "tel: bağlantısı", "tel: link"),
    ("local.source.schema", "yapılandırılmış veri", "structured data"),
    ("local.source.tel-link", "tel: bağlantısı", "tel: link"),
    ("local.source.text", "metin (sezgisel)", "text (heuristic)"),
    (
        "local.issue.schema-phone-not-on-page",
        "Yapılandırılmış veri telefonu sayfada görünen numaralardan biri değil",
        "The structured-data phone is not among the numbers shown on the page",
    ),
    (
        "local.issue.schema-phones-differ",
        "Sayfalarda farklı yapılandırılmış veri telefonları",
        "Different structured-data phones across pages",
    ),
    (
        "local.issue.schema-addresses-differ",
        "Sayfalarda farklı yapılandırılmış veri adresleri",
        "Different structured-data addresses across pages",
    ),
    (
        "local.note.phone-without-tel-link",
        "Telefon metin olarak var ama tel: bağlantısı yok.",
        "A phone number is shown as text but there is no tel: link.",
    ),
    (
        "local.note.address-from-text-is-heuristic",
        "Metinden çıkarılan adresler sezgiseldir.",
        "Addresses taken from text are heuristic.",
    ),
    ("local.col.number", "Numara", "Number"),
    ("local.col.formats", "Yazılışlar", "Spellings"),
    ("local.col.sources", "Kaynak", "Source"),
    ("local.col.pages", "Sayfa", "Pages"),
    ("local.col.address", "Adres", "Address"),
    ("local.col.issue", "Tutarsızlık", "Inconsistency"),
    ("local.col.values", "Değerler", "Values"),
    ("local.phones", "Telefonlar", "Phones"),
    ("local.addresses", "Adresler", "Addresses"),
    ("local.issues", "Tutarsızlıklar", "Inconsistencies"),
    # --- suggested sitemap
    (
        "smg.note",
        "Bu dosya yalnız örneklemde görülen sayfalardan üretilir, sitenin tamamını kapsamaz. lastmod yalnız sunucu Last-Modified başlığı gönderdiyse yazılır, tarih uydurulmaz. robots.txt engelleri burada ayrıca elenmez. Yayınlamadan önce kendi sayfa listenizle karşılaştırın.",
        "This file is built only from the pages seen in the sample and does not cover the whole site. lastmod is written only when the server sent a Last-Modified header; no date is invented. robots.txt blocks are not filtered out here. Compare it with your own page list before publishing.",
    ),
    ("smg.fact.urls", "Önerilen URL sayısı", "Suggested URLs"),
    ("smg.fact.lastmod", "lastmod bulunan", "With lastmod"),
    ("smg.fact.sample", "Örneklemdeki sayfa", "Pages in the sample"),
    ("smg.fact.existing", "Mevcut sitemap bulundu", "Existing sitemap found"),
    (
        "smg.copy",
        "Önerilen sitemap.xml (ilk {shown} URL)",
        "Suggested sitemap.xml (first {shown} URLs)",
    ),
    ("smg.download", "Tam dosyayı indir (sitemap.xml)", "Download the full file (sitemap.xml)"),
    (
        "smg.missing",
        "Sitemap'inizde olmayan uygun sayfalar",
        "Eligible pages missing from your sitemap",
    ),
    (
        "smg.not_indexable",
        "Sitemap'inizde olup indekslenemeyen sayfalar",
        "Pages in your sitemap that cannot be indexed",
    ),
    ("smg.excluded", "Önerilen dosyaya alınmayan sayfalar", "Pages left out of the suggested file"),
    ("smg.more", "… ve {n} tane daha", "… and {n} more"),
    ("smg.reason.status-4xx", "4xx yanıt", "4xx response"),
    ("smg.reason.status-5xx", "5xx yanıt", "5xx response"),
    ("smg.reason.redirected", "yönlendiriliyor", "redirects"),
    ("smg.reason.noindex", "noindex (meta)", "noindex (meta)"),
    ("smg.reason.noindex-header", "noindex (X-Robots-Tag)", "noindex (X-Robots-Tag)"),
    ("smg.reason.canonical-elsewhere", "canonical başka sayfada", "canonical points elsewhere"),
    ("smg.reason.fetch-error", "sayfa alınamadı", "page could not be fetched"),
    # --- authority
    (
        "auth.note",
        "Bu, OpenPageRank'in alan adı otoritesi tahminidir (üçüncü taraf, Common Crawl bağlantı verisinden). Google'ın bir metriği değildir, hiçbir skoru etkilemez.",
        "This is OpenPageRank's domain authority estimate (third party, built from Common Crawl link data). It is not a Google metric and affects no score.",
    ),
    ("auth.domain", "Alan adı", "Domain"),
    ("auth.pr", "Page Rank (0-10)", "Page Rank (0-10)"),
    ("auth.rank", "Küresel sıra (küçük = güçlü)", "Global rank (lower = stronger)"),
]
