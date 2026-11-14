"""EN + TR texts for the Search Console rules (fixed text; never Google data)."""

from __future__ import annotations

from seoa.domain.rules.registry import register_messages

# id -> (finding EN, TR, recommendation EN, TR, failure-check EN, TR, leading-indicator EN, TR)
_MSG: dict[str, tuple[str, str, str, str, str, str, str, str]] = {
    "gsc-page-not-indexed": (
        "Google reports that this page is not in its index (see the coverage state in the evidence).",
        "Google bu sayfanın dizininde olmadığını bildiriyor (kanıttaki kapsama durumuna bakın).",
        "Open the page in the URL Inspection tool, fix what the coverage state names (noindex, "
        "duplicate, thin or unreachable content) and request indexing.",
        "Sayfayı Search Console'daki URL Denetimi aracında açın, kapsama durumunun gösterdiği "
        "sorunu (noindex, kopya, zayıf veya erişilemeyen içerik) giderin ve dizine eklenmesini isteyin.",
        "URL Inspection reports the page as indexed.",
        "URL Denetimi sayfayı dizinde olarak bildiriyor.",
        "The number of indexed pages in the Pages report of Google Search Console.",
        "Google Search Console Sayfalar raporundaki dizindeki sayfa sayısı.",
    ),
    "gsc-canonical-mismatch": (
        "Google chose a different canonical URL than the one the page declares.",
        "Google, sayfanın bildirdiğinden farklı bir kurallı (canonical) URL seçmiş.",
        "Make the declared canonical, internal links, redirects and the sitemap point to the same "
        "URL, and keep the page content distinct from the one Google prefers.",
        "Bildirilen canonical, iç bağlantılar, yönlendirmeler ve site haritasını aynı URL'ye "
        "yönlendirin; sayfa içeriğinin Google'ın tercih ettiğinden ayrışmasını sağlayın.",
        "URL Inspection shows the Google-selected canonical equal to the declared one.",
        "URL Denetimi, Google'ın seçtiği canonical'ı bildirilenle aynı gösteriyor.",
        "'Duplicate, Google chose different canonical' count in the Pages report.",
        "Sayfalar raporundaki 'Kopya, Google farklı canonical seçti' sayısı.",
    ),
    "gsc-robots-blocked": (
        "Google reports that robots.txt blocks this page, so it cannot be crawled.",
        "Google, robots.txt'nin bu sayfayı engellediğini ve taranamadığını bildiriyor.",
        "Remove the matching Disallow rule from robots.txt if the page should be found in search.",
        "Sayfa aramada bulunmalıysa robots.txt'teki eşleşen Disallow kuralını kaldırın.",
        "URL Inspection no longer reports the page as blocked by robots.txt.",
        "URL Denetimi sayfayı artık robots.txt tarafından engellenmiş olarak bildirmiyor.",
        "'Blocked by robots.txt' count in the Pages report of Google Search Console.",
        "Google Search Console Sayfalar raporundaki 'robots.txt tarafından engellendi' sayısı.",
    ),
    "gsc-fetch-failed": (
        "Google could not fetch this page the last time it tried (server error, timeout or not found).",
        "Google bu sayfayı son denemesinde alamadı (sunucu hatası, zaman aşımı veya bulunamadı).",
        "Check that the page answers 200 quickly for Googlebot; review server logs and firewall rules.",
        "Sayfanın Googlebot'a hızlıca 200 döndüğünü kontrol edin; sunucu günlüklerini ve güvenlik "
        "duvarı kurallarını gözden geçirin.",
        "URL Inspection reports a successful page fetch.",
        "URL Denetimi başarılı bir sayfa alımı bildiriyor.",
        "Crawl stats and server-error counts in Google Search Console.",
        "Google Search Console'daki tarama istatistikleri ve sunucu hatası sayıları.",
    ),
    "gsc-sitemap-errors": (
        "A sitemap submitted in Search Console reports errors.",
        "Search Console'a gönderilmiş bir site haritası hata bildiriyor.",
        "Open the Sitemaps report, read the error and fix the file (invalid URLs, wrong format, "
        "unreachable address), then resubmit it.",
        "Site Haritaları raporunu açıp hatayı okuyun ve dosyayı düzeltin (geçersiz URL, yanlış biçim, "
        "erişilemeyen adres); ardından yeniden gönderin.",
        "The sitemap shows no errors in Search Console.",
        "Site haritası Search Console'da hata göstermiyor.",
        "Sitemap status and discovered-URL counts in the Sitemaps report.",
        "Site Haritaları raporundaki durum ve keşfedilen URL sayıları.",
    ),
    "gsc-sitemap-not-submitted": (
        "No sitemap is submitted in Search Console for this property.",
        "Bu mülk için Search Console'a hiç site haritası gönderilmemiş.",
        "Submit your sitemap in the Sitemaps report so Google finds new pages faster.",
        "Google yeni sayfaları daha hızlı bulsun diye site haritanızı Site Haritaları raporundan gönderin.",
        "The Sitemaps report lists a submitted sitemap with status Success.",
        "Site Haritaları raporu, durumu Başarılı olan gönderilmiş bir site haritası listeliyor.",
        "Discovered-URL count of the sitemap over time.",
        "Site haritasının zaman içindeki keşfedilen URL sayısı.",
    ),
    "gsc-no-impressions": (
        "The site had no search impressions in the reporting period. This is a heuristic: a new site "
        "or a very recent connection also looks like this.",
        "Site, raporlama döneminde hiç arama gösterimi almadı. Bu bir sezgidir: yeni bir site veya "
        "çok yakın zamanda yapılan bağlantı da böyle görünür.",
        "Check indexing first (Pages report); give a new site a few weeks, then improve content "
        "and internal links for the queries you want to reach.",
        "Önce dizine eklenmeyi kontrol edin (Sayfalar raporu); yeni siteye birkaç hafta tanıyın, "
        "ardından hedef sorgular için içeriği ve iç bağlantıları geliştirin.",
        "Impressions greater than zero in the Performance report.",
        "Performans raporunda sıfırdan büyük gösterim.",
        "Impressions and average position in the Performance report over several weeks.",
        "Performans raporundaki gösterim ve ortalama konum, birkaç hafta boyunca.",
    ),
}


def _register() -> None:
    entries: dict[str, dict[str, str]] = {}
    for rid, (fe, ft, re_, rt, ce, ct, le, lt) in _MSG.items():
        entries[f"finding.{rid}"] = {"en": fe, "tr": ft}
        entries[f"rec.{rid}"] = {"en": re_, "tr": rt}
        entries[f"fail.{rid}"] = {"en": ce, "tr": ct}
        entries[f"lead.{rid}"] = {"en": le, "tr": lt}
    register_messages(entries)


_register()
