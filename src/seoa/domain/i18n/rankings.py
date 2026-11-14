"""TR + EN strings for the keyword rankings section (belge 12 B1)."""

from __future__ import annotations

# (key, tr, en)
ENTRIES: list[tuple[str, str, str]] = [
    ("sec.rankings", "Sıralama", "Rankings"),
    (
        "reason.rankings-gsc-required",
        "Ölçülmedi: Search Console bağlı değil. Sıralama yalnızca sahibi olduğunuz, doğrulanmış sitenin Search Console verisiyle ölçülür; başkasının sıralaması ücretsiz ve güvenilir biçimde ölçülemez.",
        "Not measured: Search Console is not connected. Rankings come only from the Search Console data of a verified site you own; someone else's rankings cannot be measured reliably for free.",
    ),
    (
        "reason.rankings-no-keywords",
        'Ölçülmedi: anahtar kelime girilmedi (ve Search Console\'da listelenecek fırsat sorgusu yok). Arama formundaki "Anahtar kelimeler" alanına kelime yazıp denetimi yeniden çalıştırın.',
        'Not measured: no keywords were entered (and Search Console has no opportunity queries to list). Add keywords in the "Keywords" field of the search form and rerun the audit.',
    ),
    (
        "reason.rankings-not-run",
        "Bu denetimde sıralama verisi alınmadı (denetim sıralama desteğinden önce yapılmış olabilir). Denetimi yeniden çalıştırın.",
        "No ranking data was fetched in this audit (it may predate ranking support). Rerun the audit.",
    ),
    (
        "rank.note",
        "Yalnızca Search Console verisi (son {days} gün, 2-3 günlük gecikmeyle). Konum ortalamadır; bilgi amaçlıdır ve skora girmez.",
        "Search Console data only (last {days} days, with a 2-3 day lag). Position is an average; informational, not part of the score.",
    ),
    (
        "rank.kw.title",
        "Anahtar kelimeleriniz",
        "Your keywords",
    ),
    ("rank.kw.none", "Anahtar kelime girilmedi.", "No keywords were entered."),
    ("rank.col.keyword", "Anahtar kelime", "Keyword"),
    ("rank.col.page", "En iyi sayfa", "Top page"),
    ("rank.col.status", "Durum", "Status"),
    ("rank.status.ok", "Veri var", "Data"),
    (
        "rank.status.no-data",
        "Veri yok: son {days} günde bu sorgu için kayıt yok. Search Console düşük hacimli sorguları gizler; bu, sıralamadığınız anlamına gelmez.",
        "No data: no record for this query in the last {days} days. Search Console hides low-volume queries; this does not mean you do not rank.",
    ),
    ("rank.status.error", "Alınamadı", "Not fetched"),
    ("rank.error.rate-limited", "istek sınırı aşıldı", "rate limit reached"),
    ("rank.error.no-permission", "izin yok", "no permission"),
    ("rank.error.property-not-found", "mülk bulunamadı", "property not found"),
    ("rank.error.not-connected", "bağlantı yok", "not connected"),
    ("rank.error.timeout", "zaman aşımı", "timeout"),
    ("rank.error.unreachable", "ulaşılamadı", "unreachable"),
    (
        "rank.matched",
        "tam eşleşme yok; en çok gösterilen içeren sorgu: {query}",
        "no exact match; most-shown query containing it: {query}",
    ),
    (
        "rank.opp.title",
        "Sıralama fırsatları",
        "Ranking opportunities",
    ),
    (
        "rank.opp.rule",
        "Sezgisel kural: ortalama konum 4-20 ve en az {min} gösterim. İlk 10'a veya ilk 3'e yakın sorgular; bu bir tahmindir, Google bir eşik yayınlamaz.",
        "Heuristic: average position 4-20 with at least {min} impressions. Queries close to page one or to the top three; an estimate, Google publishes no threshold.",
    ),
    ("rank.low.title", "Düşük tıklama oranı", "Low click-through rate"),
    (
        "rank.low.rule",
        "Sezgisel kural: konum 1-3 iken TO < %{top3}, konum 4-10 iken TO < %{top10} (en az {min} gösterim). Başlık ve açıklamayı gözden geçirmeye değer; bunlar ortalama değerlerdir.",
        "Heuristic: CTR below {top3}% at positions 1-3 or below {top10}% at positions 4-10 (at least {min} impressions). Worth reviewing the title and description; these are averages.",
    ),
    ("rank.none.list", "Bu ölçütlere uyan sorgu yok.", "No query matches this rule."),
    (
        "rank.keywords.missing",
        "Anahtar kelime girilmedi: aşağıda yalnızca sitenin kendi sorgularından çıkarılan fırsatlar var.",
        "No keywords were entered: below are only the opportunities taken from the site's own queries.",
    ),
    (
        "rank.list.error",
        "Sorgu listesi alınamadı ({code}).",
        "The query list could not be fetched ({code}).",
    ),
    ("rank.col.query", "Sorgu", "Query"),
]
