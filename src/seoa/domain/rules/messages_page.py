"""EN/TR message catalogue for the 47 page rules (the upstream project page_checks.py messages, ported).

English texts are the source's, with its f-string thresholds expanded. Turkish texts are our
translation. ``finding.<id>`` = what was observed, ``rec.<id>`` = what to do. Fixed texts only:
page data never goes into a message (it goes into ``evidence``).
"""

from __future__ import annotations

from seoa.domain.rules.registry import register_messages

_H = "This is a display heuristic, not a published search engine limit."
_H_TR = "Bu bir gösterim sezgisidir, yayımlanmış bir arama motoru sınırı değildir."

# (id, EN finding, TR finding, EN recommendation, TR recommendation)
_RULES: list[tuple[str, str, str, str, str]] = [
    (
        "missing-title",
        "The page has no title tag. Search engines then build the result title from other text, such as the main heading.",
        "Sayfada title etiketi yok. Arama motorları sonuç başlığını bu durumda ana başlık gibi başka metinlerden üretir.",
        "Add a unique, descriptive <title> of roughly 30 to 60 characters.",
        "Sayfaya yaklaşık 30-60 karakterlik, benzersiz ve açıklayıcı bir <title> ekleyin.",
    ),
    (
        "title-too-long",
        f"The title is longer than 60 characters and may be truncated in results. {_H}",
        f"Başlık 60 karakterden uzun ve sonuçlarda kısaltılabilir. {_H_TR}",
        "Shorten the title and put the most important words first.",
        "Başlığı kısaltın ve en önemli sözcükleri başa alın.",
    ),
    (
        "title-too-short",
        "The title is shorter than 30 characters. A very short title rarely describes the page well enough to earn a click. This is a heuristic, not a search engine rule.",
        "Başlık 30 karakterden kısa. Çok kısa bir başlık sayfayı tıklama kazanacak kadar iyi anlatmaz. Bu bir sezgidir, arama motoru kuralı değildir.",
        "Expand the title so it says what the page offers.",
        "Başlığı, sayfanın ne sunduğunu anlatacak şekilde genişletin.",
    ),
    (
        "missing-meta-description",
        "The page has no meta description. Search engines write their own snippet when none is given.",
        "Sayfada meta açıklaması yok. Arama motorları açıklama verilmezse kendi özetini yazar.",
        "Write a meta description of about 120 to 160 characters for this page.",
        "Bu sayfa için yaklaşık 120-160 karakterlik bir meta açıklaması yazın.",
    ),
    (
        "meta-description-too-long",
        f"The meta description is longer than 160 characters and may be truncated in results. {_H}",
        f"Meta açıklaması 160 karakterden uzun ve sonuçlarda kısaltılabilir. {_H_TR}",
        "Shorten the description and lead with the key message.",
        "Açıklamayı kısaltın ve ana mesajla başlayın.",
    ),
    (
        "duplicate-meta-tags",
        "The same title, meta tag or canonical appears more than once, so it is unclear which one search engines and social platforms read.",
        "Aynı title, meta etiketi veya canonical birden fazla kez geçiyor; arama motorlarının ve sosyal platformların hangisini okuduğu belirsiz.",
        "Keep exactly one of each; remove the duplicates (often added by both a theme and a plugin).",
        "Her birinden yalnızca bir tane bırakın, kopyaları kaldırın (çoğunlukla hem tema hem eklenti ekler).",
    ),
    (
        "missing-h1",
        "No H1 heading was found on the page.",
        "Sayfada H1 başlığı bulunamadı.",
        "Add one H1 that names the page.",
        "Sayfayı adlandıran bir H1 ekleyin.",
    ),
    (
        "multiple-h1",
        "The page has more than one H1. Google says there is no ideal number of headings, so this does not affect Search on its own. Check that the most prominent heading names the page.",
        "Sayfada birden fazla H1 var. Google ideal bir başlık sayısı olmadığını söyler, bu tek başına Arama'yı etkilemez. En belirgin başlığın sayfayı adlandırdığından emin olun.",
        "Make sure the most prominent heading names the page; demote others if they are not page titles.",
        "En belirgin başlığın sayfayı adlandırdığından emin olun; sayfa başlığı olmayanları alt seviyeye alın.",
    ),
    (
        "heading-level-skip",
        "Heading levels skip inside the main content, for example from H2 to H4. Google Search does not mind heading order, but screen reader users move through a page by heading level.",
        "Ana içerikte başlık seviyeleri atlanıyor (örneğin H2'den H4'e). Google Arama başlık sırasına takılmaz, ama ekran okuyucu kullanıcıları sayfada başlık seviyesine göre gezinir.",
        "Use consecutive heading levels (H2 then H3, not H2 then H4).",
        "Ardışık başlık seviyeleri kullanın (H2'den sonra H3, H4 değil).",
    ),
    (
        "missing-canonical",
        "The page has no canonical link. Search engines then choose the preferred URL themselves.",
        "Sayfada canonical bağlantısı yok. Arama motorları bu durumda tercih edilen URL'yi kendileri seçer.",
        'Add a self-referencing <link rel="canonical"> with the preferred absolute URL.',
        'Tercih edilen mutlak URL\'yi gösteren, kendine referans veren bir <link rel="canonical"> ekleyin.',
    ),
    (
        "canonical-points-elsewhere",
        "The canonical names a different URL, so this page asks search engines to index that URL instead. Confirm this is intended.",
        "Canonical başka bir URL'yi gösteriyor; bu sayfa arama motorlarından onun yerine o URL'yi dizinlemelerini istiyor. Bunun bilinçli olduğundan emin olun.",
        "If this page should be indexed, point its canonical at itself; otherwise confirm the target is the right page.",
        "Bu sayfa dizinlenecekse canonical'ı kendisine yönlendirin; değilse hedefin doğru sayfa olduğunu doğrulayın.",
    ),
    (
        "og-url-differs-from-canonical",
        "og:url differs from the canonical, so social shares may point at a different URL than search engines use.",
        "og:url canonical'dan farklı; sosyal paylaşımlar arama motorlarının kullandığından farklı bir URL'ye işaret edebilir.",
        "Set og:url to the same URL as the canonical.",
        "og:url'yi canonical ile aynı URL'ye ayarlayın.",
    ),
    (
        "noindex",
        "A robots meta tag asks search engines not to index this page. Confirm this is intended.",
        "Bir robots meta etiketi arama motorlarından bu sayfayı dizinlememelerini istiyor. Bunun bilinçli olduğundan emin olun.",
        "Remove the noindex directive if the page should appear in search results.",
        "Sayfa arama sonuçlarında görünecekse noindex yönergesini kaldırın.",
    ),
    (
        "noindex-header",
        "The X-Robots-Tag response header asks search engines not to index this page. Confirm this is intended.",
        "X-Robots-Tag yanıt başlığı arama motorlarından bu sayfayı dizinlememelerini istiyor. Bunun bilinçli olduğundan emin olun.",
        "Remove the noindex from the X-Robots-Tag header (server or CDN configuration) if the page should be indexed.",
        "Sayfa dizinlenecekse X-Robots-Tag başlığındaki noindex'i (sunucu veya CDN ayarı) kaldırın.",
    ),
    (
        "nofollow",
        "The page asks search engines not to follow any of its links. Confirm this is intended.",
        "Sayfa arama motorlarından hiçbir bağlantısını izlememelerini istiyor. Bunun bilinçli olduğundan emin olun.",
        "Remove nofollow from the robots directive unless you really want none of the links followed.",
        "Hiçbir bağlantının izlenmemesini gerçekten istemiyorsanız robots yönergesinden nofollow'u kaldırın.",
    ),
    (
        "meta-refresh-redirect",
        "The page redirects with a meta refresh. Google follows it, but a server side 301 or 308 redirect is the more reliable choice.",
        "Sayfa meta refresh ile yönlendiriyor. Google bunu izler, ama sunucu tarafı 301 veya 308 yönlendirmesi daha güvenilirdir.",
        "Replace the meta refresh with a server-side 301 or 308 redirect.",
        "Meta refresh'i sunucu tarafı 301 veya 308 yönlendirmesiyle değiştirin.",
    ),
    (
        "hreflang-missing-self",
        "The page has hreflang links but none of them points to the page itself. Hreflang sets should include a self reference.",
        "Sayfada hreflang bağlantıları var ama hiçbiri sayfanın kendisini göstermiyor. Hreflang kümeleri kendine referans içermelidir.",
        "Add a hreflang entry for this page's own language and URL.",
        "Bu sayfanın kendi dili ve URL'si için bir hreflang girdisi ekleyin.",
    ),
    (
        "missing-doctype",
        "The document does not start with <!doctype html>, so browsers fall back to quirks mode.",
        "Belge <!doctype html> ile başlamıyor, bu yüzden tarayıcılar quirks moduna düşer.",
        "Start the document with <!doctype html>.",
        "Belgeyi <!doctype html> ile başlatın.",
    ),
    (
        "missing-charset",
        "No character encoding is declared for the document.",
        "Belge için karakter kodlaması belirtilmemiş.",
        'Declare <meta charset="utf-8"> in the first 1024 bytes of the head.',
        'head\'in ilk 1024 baytı içinde <meta charset="utf-8"> tanımlayın.',
    ),
    (
        "charset-mismatch",
        "The Content-Type response header and the meta tag declare different character encodings.",
        "Content-Type yanıt başlığı ile meta etiketi farklı karakter kodlamaları bildiriyor.",
        "Declare the same encoding (utf-8) in the header and the meta tag.",
        "Başlıkta ve meta etiketinde aynı kodlamayı (utf-8) bildirin.",
    ),
    (
        "missing-lang",
        "The html element does not declare the page language with a lang attribute.",
        "html öğesi sayfa dilini lang özniteliğiyle belirtmiyor.",
        'Add a lang attribute to <html> (for example lang="tr").',
        '<html> öğesine lang özniteliği ekleyin (örneğin lang="tr").',
    ),
    (
        "missing-viewport",
        "The page has no viewport meta tag, so phones render it zoomed out.",
        "Sayfada viewport meta etiketi yok, bu yüzden telefonlar sayfayı uzaklaştırılmış gösterir.",
        'Add <meta name="viewport" content="width=device-width, initial-scale=1">.',
        '<meta name="viewport" content="width=device-width, initial-scale=1"> ekleyin.',
    ),
    (
        "uses-frames",
        "The page uses frames. Content inside frames is hard for search engines to attribute to this URL.",
        "Sayfa frame kullanıyor. Frame içindeki içeriği bu URL'ye atfetmek arama motorları için zordur.",
        "Replace frames with normal page markup or server-side includes.",
        "Frame'leri normal sayfa işaretlemesi veya sunucu tarafı include ile değiştirin.",
    ),
    (
        "deprecated-html-tags",
        "The page uses HTML tags that are obsolete, such as <center> or <font>.",
        "Sayfa <center> veya <font> gibi artık kullanılmayan HTML etiketleri kullanıyor.",
        "Replace obsolete tags with CSS.",
        "Eski etiketleri CSS ile değiştirin.",
    ),
    (
        "placeholder-text",
        "Placeholder text such as lorem ipsum was found in the visible content.",
        "Görünür içerikte lorem ipsum gibi yer tutucu metin bulundu.",
        "Replace the placeholder text with real content before the page is indexed.",
        "Sayfa dizinlenmeden önce yer tutucu metni gerçek içerikle değiştirin.",
    ),
    (
        "images-missing-alt",
        "Some images have no alt attribute. Screen readers and image search rely on alt text. An empty alt is correct for decorative images.",
        "Bazı görsellerde alt özniteliği yok. Ekran okuyucular ve görsel arama alt metne dayanır. Dekoratif görsellerde boş alt doğrudur.",
        'Add descriptive alt text to content images; use alt="" for decorative ones.',
        'İçerik görsellerine açıklayıcı alt metin ekleyin; dekoratif olanlarda alt="" kullanın.',
    ),
    (
        "images-missing-dimensions",
        "Some images have no width and height attributes, which lets the layout shift while they load.",
        "Bazı görsellerde width ve height öznitelikleri yok, bu da yüklenirken düzenin kaymasına yol açar.",
        "Set width and height attributes (or CSS aspect-ratio) on images.",
        "Görsellere width ve height öznitelikleri (veya CSS aspect-ratio) ekleyin.",
    ),
    (
        "first-image-lazy-loaded",
        "The first image in the main content is lazy loaded. It is often the largest paint, and lazy loading delays it.",
        "Ana içerikteki ilk görsel tembel (lazy) yükleniyor. Genellikle en büyük çizim odur ve tembel yükleme onu geciktirir.",
        'Remove loading="lazy" from the first, above-the-fold image.',
        'İlk, ekranın üst kısmındaki görselden loading="lazy" özniteliğini kaldırın.',
    ),
    (
        "links-without-text",
        "Some links have no accessible text: no link text, no label and no image alt text.",
        "Bazı bağlantılarda erişilebilir metin yok: bağlantı metni, etiket ve görsel alt metni yok.",
        "Give every link visible text or an aria-label.",
        "Her bağlantıya görünür bir metin veya aria-label verin.",
    ),
    (
        "generic-anchor-text",
        'Some links in the content use generic text such as "click here", which says nothing about where they lead.',
        'İçerikteki bazı bağlantılar "buraya tıklayın" gibi genel metinler kullanıyor; bunlar bağlantının nereye gittiğini anlatmaz.',
        "Rewrite generic link text to describe the destination.",
        "Genel bağlantı metinlerini hedefi anlatacak şekilde yeniden yazın.",
    ),
    (
        "links-to-http",
        "This HTTPS page links to plain http:// addresses.",
        "Bu HTTPS sayfası düz http:// adreslerine bağlantı veriyor.",
        "Update links to the https:// version of the target.",
        "Bağlantıları hedefin https:// sürümüne güncelleyin.",
    ),
    (
        "mixed-content",
        "This HTTPS page loads resources over plain HTTP. Browsers block or warn about these.",
        "Bu HTTPS sayfası kaynakları düz HTTP üzerinden yüklüyor. Tarayıcılar bunları engeller veya uyarı verir.",
        "Load every resource over https://.",
        "Tüm kaynakları https:// üzerinden yükleyin.",
    ),
    (
        "url-too-long",
        "The URL is longer than 100 characters. Long URLs are harder to share and may be truncated in results. This is a heuristic, not a search engine limit.",
        "URL 100 karakterden uzun. Uzun URL'ler paylaşması zordur ve sonuçlarda kısaltılabilir. Bu bir sezgidir, arama motoru sınırı değildir.",
        "Shorten the URL path where you can.",
        "URL yolunu mümkün olduğunca kısaltın.",
    ),
    (
        "url-has-parameters",
        "The URL has query parameters other than tracking parameters. Parameters can create duplicate versions of the same page.",
        "URL'de izleme dışı sorgu parametreleri var. Parametreler aynı sayfanın yinelenen sürümlerini oluşturabilir.",
        "Make sure parameter variants canonicalise to one URL.",
        "Parametreli varyantların tek bir URL'ye canonical olduğundan emin olun.",
    ),
    (
        "url-uppercase",
        "The URL path has uppercase letters. URLs are case sensitive, so mixed case invites duplicates and broken links.",
        "URL yolunda büyük harfler var. URL'ler büyük/küçük harfe duyarlıdır, karışık yazım yinelenen ve kırık bağlantılara yol açar.",
        "Use lower-case paths and redirect the old form.",
        "Küçük harfli yollar kullanın ve eski biçimi yönlendirin.",
    ),
    (
        "url-underscores",
        "The URL path uses underscores. Hyphens are the usual word separator in URLs.",
        "URL yolu alt çizgi kullanıyor. URL'lerde olağan sözcük ayırıcı tiredir.",
        "Use hyphens between words and redirect the old URL.",
        "Sözcükler arasında tire kullanın ve eski URL'yi yönlendirin.",
    ),
    (
        "url-non-ascii",
        "The URL has unencoded non-ASCII characters. Words in the audience's language are fine in URLs; links should use the percent encoded form so the address survives copying.",
        "URL'de kodlanmamış ASCII dışı karakterler var. Hedef kitlenin dilindeki sözcükler URL'de sorun değildir; adres kopyalanınca bozulmasın diye bağlantılar yüzde-kodlu biçimi kullanmalı.",
        "Link to the percent-encoded form of the URL.",
        "URL'nin yüzde-kodlu biçimine bağlantı verin.",
    ),
    (
        "url-double-slash",
        "The URL path has a double slash, which often creates accidental duplicate URLs.",
        "URL yolunda çift eğik çizgi var; bu çoğu zaman kazara yinelenen URL'ler oluşturur.",
        "Remove the double slash and redirect the old URL.",
        "Çift eğik çizgiyi kaldırın ve eski URL'yi yönlendirin.",
    ),
    (
        "html-over-2mb",
        "The HTML is larger than 2 MB. Googlebot reads only the first 2 MB of an HTML file, measured before compression, so content after that point is not considered for indexing.",
        "HTML 2 MB'tan büyük. Googlebot bir HTML dosyasının yalnızca ilk 2 MB'ını (sıkıştırma öncesi) okur; bu noktadan sonraki içerik dizinleme için dikkate alınmaz.",
        "Move inline scripts, styles and data out of the HTML and trim the markup below 2 MB.",
        "Satır içi betik, stil ve verileri HTML dışına taşıyın ve işaretlemeyi 2 MB altına indirin.",
    ),
    (
        "deep-dom",
        "The DOM is nested more than 32 levels deep, which slows rendering (Lighthouse guidance).",
        "DOM 32 seviyeden derin iç içe; bu render'ı yavaşlatır (Lighthouse önerisi).",
        "Flatten the markup structure.",
        "İşaretleme yapısını düzleştirin.",
    ),
    (
        "wide-dom-node",
        "One element has more than 60 direct children, which is slow to lay out (Lighthouse guidance).",
        "Bir öğenin 60'tan fazla doğrudan çocuğu var; bu yerleşimi yavaşlatır (Lighthouse önerisi).",
        "Group or paginate very long lists of siblings.",
        "Çok uzun kardeş listelerini gruplayın veya sayfalayın.",
    ),
    (
        "missing-open-graph",
        "The page has neither og:title nor og:image, so shared links show no title or preview image.",
        "Sayfada ne og:title ne de og:image var, bu yüzden paylaşılan bağlantılarda başlık veya önizleme görseli görünmez.",
        "Add og:title, og:description and og:image.",
        "og:title, og:description ve og:image ekleyin.",
    ),
    (
        "missing-og-image",
        "The page has no og:image, so shared links show no preview image.",
        "Sayfada og:image yok, bu yüzden paylaşılan bağlantılarda önizleme görseli görünmez.",
        "Add an og:image (about 1200x630 px).",
        "Bir og:image ekleyin (yaklaşık 1200x630 px).",
    ),
    (
        "invalid-jsonld",
        "A JSON-LD block is not valid JSON, so search engines cannot read any of it and the page loses the rich result that block was meant to support.",
        "Bir JSON-LD bloğu geçerli JSON değil; arama motorları bloğun hiçbirini okuyamaz ve sayfa o bloğun desteklemesi gereken zengin sonucu kaybeder.",
        "Fix the JSON syntax of the block and validate it.",
        "Bloğun JSON sözdizimini düzeltin ve doğrulayın.",
    ),
    (
        "title-not-reflected-in-content",
        "Most significant words of the title do not appear in the visible page text.",
        "Başlığın anlamlı sözcüklerinin çoğu görünür sayfa metninde geçmiyor.",
        "Make the title and the page text talk about the same topic.",
        "Başlık ile sayfa metninin aynı konudan söz etmesini sağlayın.",
    ),
    (
        "description-not-reflected-in-content",
        "Most significant words of the meta description do not appear in the visible page text.",
        "Meta açıklamasının anlamlı sözcüklerinin çoğu görünür sayfa metninde geçmiyor.",
        "Rewrite the description so it summarises what is on the page.",
        "Açıklamayı sayfada olanı özetleyecek şekilde yeniden yazın.",
    ),
    (
        "thin-content",
        "The page has fewer than 200 words of visible body text. Google has no minimum word count, so this is not a ranking rule. Check that the page fully answers what a visitor came for.",
        "Sayfada 200 kelimeden az görünür gövde metni var. Google'ın asgari kelime sayısı yoktur, bu bir sıralama kuralı değildir. Sayfanın ziyaretçinin aradığını tam yanıtladığını kontrol edin.",
        "Check that the page fully answers the visitor's question; expand it if it does not.",
        "Sayfanın ziyaretçinin sorusunu tam yanıtladığını kontrol edin; yanıtlamıyorsa genişletin.",
    ),
]

# Shared templates (belge 03 s.7.1): the "how would we know this failed" and leading indicators.
_COMMON = {
    "failure_check.rescan": {
        "en": "Re-run the audit: this finding must no longer appear for the page.",
        "tr": "Denetimi yeniden çalıştırın: bu bulgu sayfa için artık görünmemeli.",
    },
    "leading_indicator.technical": {
        "en": "Indexed page count and crawl errors in Search Console move in the right direction.",
        "tr": "Search Console'daki dizinlenen sayfa sayısı ve tarama hataları doğru yönde değişir.",
    },
    "leading_indicator.onpage": {
        "en": "Impressions and click-through rate of the page in Search Console.",
        "tr": "Sayfanın Search Console'daki gösterim ve tıklama oranı.",
    },
    "leading_indicator.content": {
        "en": "Engagement on the page (time on page, scroll depth) and impressions for its topic.",
        "tr": "Sayfadaki etkileşim (sayfada kalma süresi, kaydırma derinliği) ve konusuna ait gösterimler.",
    },
    "leading_indicator.schema": {
        "en": "Rich result validity reports in Search Console.",
        "tr": "Search Console'daki zengin sonuç geçerlilik raporları.",
    },
    "leading_indicator.images": {
        "en": "Image search impressions and Cumulative Layout Shift in field data.",
        "tr": "Görsel arama gösterimleri ve saha verisindeki Cumulative Layout Shift.",
    },
    "leading_indicator.performance": {
        "en": "Core Web Vitals field data (LCP, INP, CLS) for the page.",
        "tr": "Sayfanın Core Web Vitals saha verisi (LCP, INP, CLS).",
    },
    "leading_indicator.ai_readiness": {
        "en": "Fetches by AI search crawlers in server logs.",
        "tr": "Sunucu günlüklerinde yapay zekâ arama tarayıcılarının istekleri.",
    },
}


def _register() -> None:
    entries: dict[str, dict[str, str]] = dict(_COMMON)
    for rule_id, en, tr, rec_en, rec_tr in _RULES:
        entries[f"finding.{rule_id}"] = {"en": en, "tr": tr}
        entries[f"rec.{rule_id}"] = {"en": rec_en, "tr": rec_tr}
    register_messages(entries)


_register()
RULE_IDS: tuple[str, ...] = tuple(r[0] for r in _RULES)
