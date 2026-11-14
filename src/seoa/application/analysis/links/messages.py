"""EN + TR texts for the link and duplicate-content rules (fixed text; never page data)."""

from __future__ import annotations

from seoa.domain.rules.registry import register_messages

# id -> (finding EN, finding TR, recommendation EN, recommendation TR,
#        failure-check EN, failure-check TR, leading-indicator EN, leading-indicator TR)
_MSG: dict[str, tuple[str, str, str, str, str, str, str, str]] = {
    "broken-internal-link": (
        "The page links to an internal URL that answers with an error (for example 404) or cannot be reached.",
        "Sayfa, hata veren (örneğin 404) veya erişilemeyen bir iç URL'ye bağlanıyor.",
        "Fix or redirect the broken URL, or change the link to the page's current address.",
        "Bozuk URL'yi düzeltin veya yönlendirin ya da bağlantıyı sayfanın güncel adresine çevirin.",
        "A fresh audit no longer lists this link as broken.",
        "Yeni bir denetim bu bağlantıyı artık kırık olarak listelemiyor.",
        "Crawl errors and 'Not found (404)' counts in Google Search Console.",
        "Google Search Console'daki tarama hataları ve 'Bulunamadı (404)' sayıları.",
    ),
    "broken-external-link": (
        "The page links to an external URL that answers with an error or cannot be reached. This can be temporary.",
        "Sayfa, hata veren veya erişilemeyen bir dış URL'ye bağlanıyor. Bu geçici olabilir.",
        "Check the link in a browser; update it, replace it or remove it if the target is gone.",
        "Bağlantıyı tarayıcıda kontrol edin; hedef kaybolduysa güncelleyin, değiştirin veya kaldırın.",
        "A fresh audit no longer lists this external link as broken.",
        "Yeni bir denetim bu dış bağlantıyı artık kırık olarak listelemiyor.",
        "The number of broken external links in repeated audits.",
        "Tekrarlanan denetimlerdeki kırık dış bağlantı sayısı.",
    ),
    "internal-redirect-link": (
        "An internal link points to a URL that redirects before reaching the page.",
        "Bir iç bağlantı, sayfaya ulaşmadan önce yönlendirilen bir URL'yi gösteriyor.",
        "Link directly to the final URL so visitors and crawlers skip the redirect.",
        "Ziyaretçiler ve tarayıcılar yönlendirmeyi atlasın diye doğrudan son URL'ye bağlantı verin.",
        "A fresh audit no longer lists this link as redirecting.",
        "Yeni bir denetim bu bağlantıyı artık yönlendirmeli olarak listelemiyor.",
        "The number of internal links that redirect in repeated audits.",
        "Tekrarlanan denetimlerdeki yönlendirilen iç bağlantı sayısı.",
    ),
    "orphan-page": (
        "A URL listed in the sitemap is not linked from any page in the sample. This is a heuristic: the sample may not include every page.",
        "Site haritasında listelenen bir URL'ye örneklemdeki hiçbir sayfadan bağlantı verilmiyor. Bu bir sezgidir: örnekleme her sayfa dahil olmayabilir.",
        "Link to the page from relevant pages, or remove it from the sitemap if it should not be indexed.",
        "Sayfaya ilgili sayfalardan bağlantı verin veya indekslenmemesi gerekiyorsa site haritasından çıkarın.",
        "A fresh audit finds at least one internal link to the page.",
        "Yeni bir denetim sayfaya en az bir iç bağlantı buluyor.",
        "Internal links pointing to the page in the Links report of Google Search Console.",
        "Google Search Console Bağlantılar raporunda sayfaya işaret eden iç bağlantılar.",
    ),
    "deep-page": (
        "The page needs more than three clicks from the entry page in the sampled link graph. This is a heuristic, not a search engine rule.",
        "Sayfa, örneklenen bağlantı grafiğinde giriş sayfasından üçten fazla tık uzaklıkta. Bu bir sezgidir, arama motoru kuralı değildir.",
        "Link important pages from the home page or the main navigation to bring them closer.",
        "Önemli sayfalara ana sayfadan veya ana gezinmeden bağlantı vererek onları yaklaştırın.",
        "A fresh audit measures a click depth of three or less for the page.",
        "Yeni bir denetim sayfa için üç veya daha az tık derinliği ölçüyor.",
        "The maximum click depth reported by repeated audits.",
        "Tekrarlanan denetimlerde bildirilen en büyük tık derinliği.",
    ),
    "too-many-links": (
        "The page has more than 150 links. This is a heuristic, not a limit set by search engines.",
        "Sayfada 150'den fazla bağlantı var. Bu bir sezgidir, arama motorlarının koyduğu bir sınır değildir.",
        "Check that every link helps the visitor; trim repeated or decorative links and large link lists.",
        "Her bağlantının ziyaretçiye yardımcı olduğunu kontrol edin; tekrarlanan veya süs amaçlı bağlantıları ve büyük bağlantı listelerini azaltın.",
        "A fresh audit counts 150 links or fewer on the page.",
        "Yeni bir denetim sayfada 150 veya daha az bağlantı sayıyor.",
        "The number of links per page in repeated audits.",
        "Tekrarlanan denetimlerde sayfa başına bağlantı sayısı.",
    ),
    "no-internal-links": (
        "The page has no links to other pages of the site.",
        "Sayfanın sitenin diğer sayfalarına hiç bağlantısı yok.",
        "Add links to related pages or to the main sections so visitors and crawlers can continue.",
        "Ziyaretçiler ve tarayıcılar devam edebilsin diye ilgili sayfalara veya ana bölümlere bağlantı ekleyin.",
        "A fresh audit finds at least one internal link on the page.",
        "Yeni bir denetim sayfada en az bir iç bağlantı buluyor.",
        "Pages per session and exit rate of the page in your analytics.",
        "Analitiğinizde sayfanın oturum başına sayfa sayısı ve çıkış oranı.",
    ),
    "nofollow-internal-links": (
        "At least a fifth of the page's internal links carry rel=nofollow. This is a heuristic.",
        "Sayfadaki iç bağlantıların en az beşte biri rel=nofollow taşıyor. Bu bir sezgidir.",
        "Check that nofollow on internal links is intentional; links to pages you want indexed are normally left followed.",
        "İç bağlantılardaki nofollow'un bilinçli olduğunu kontrol edin; indekslenmesini istediğiniz sayfalara giden bağlantılar normalde takip edilebilir bırakılır.",
        "A fresh audit shows fewer nofollow internal links on the page.",
        "Yeni bir denetim sayfada daha az nofollow iç bağlantı gösteriyor.",
        "The share of nofollow internal links in repeated audits.",
        "Tekrarlanan denetimlerde nofollow iç bağlantı payı.",
    ),
    "placeholder-links": (
        'Several links with visible text point nowhere (href="#" or javascript:void). Visitors and crawlers cannot follow them. This is a heuristic: a link may be wired to a script.',
        'Görünür metni olan birkaç bağlantı hiçbir yere gitmiyor (href="#" veya javascript:void). Ziyaretçiler ve tarayıcılar bu bağlantıları izleyemez. Bu bir sezgidir: bağlantı bir betiğe bağlı olabilir.',
        "Point each link to a real page (for example the privacy policy, terms or contact page), or turn it into a button if it only runs a script.",
        "Her bağlantıyı gerçek bir sayfaya (örneğin gizlilik, koşullar veya iletişim sayfası) bağlayın; yalnızca bir betik çalıştırıyorsa düğmeye çevirin.",
        'A fresh audit finds no links that point to "#" or javascript:void.',
        'Yeni bir denetim "#" veya javascript:void\'e giden bağlantı bulmuyor.',
        "Visitors reaching the legal and contact pages, and the click rate on these links in your analytics.",
        "Ziyaretçilerin yasal ve iletişim sayfalarına ulaşması ve bu bağlantıların analitikteki tıklanma oranı.",
    ),
    "duplicate-content": (
        "The main text is very similar to another page in the sample (word-shingle overlap of 85% or more). The threshold is a heuristic.",
        "Ana metin, örneklemdeki başka bir sayfaya çok benziyor (kelime öbeği örtüşmesi %85 veya üzeri). Eşik bir sezgidir.",
        "Merge the pages, make their content distinct, or point a canonical at the preferred version.",
        "Sayfaları birleştirin, içeriklerini birbirinden ayırın veya tercih edilen sürümü canonical ile belirtin.",
        "A fresh audit no longer finds the two pages above the similarity threshold.",
        "Yeni bir denetim iki sayfayı artık benzerlik eşiğinin üzerinde bulmuyor.",
        "The number of near-duplicate page pairs in repeated audits.",
        "Tekrarlanan denetimlerdeki yakın kopya sayfa çifti sayısı.",
    ),
}


def _register() -> None:
    entries: dict[str, dict[str, str]] = {}
    for rid, (m_en, m_tr, r_en, r_tr, f_en, f_tr, l_en, l_tr) in _MSG.items():
        entries[f"finding.{rid}"] = {"en": m_en, "tr": m_tr}
        entries[f"rec.{rid}"] = {"en": r_en, "tr": r_tr}
        entries[f"fail.{rid}"] = {"en": f_en, "tr": f_tr}
        entries[f"lead.{rid}"] = {"en": l_en, "tr": l_tr}
    register_messages(entries)


_register()
MESSAGE_RULE_IDS = tuple(_MSG)
