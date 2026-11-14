"""EN + TR texts for the lab performance, image and mobile rules."""

from __future__ import annotations

from seoa.application.analysis.performance import rules as rules_perf
from seoa.domain.rules.registry import register_messages

_MSG = {
    "page-weight-heavy": (
        "The page transfers more than 3 MiB in total. This limit is a heuristic, not a search engine rule.",
        "Sayfa toplamda 3 MiB'den fazla veri aktarıyor. Bu sınır bir sezgidir, arama motoru kuralı değildir.",
        "Cut the largest transfers first (images, scripts, fonts, video); lazy-load below-the-fold media.",
        "Önce en büyük aktarımları azaltın (görseller, script'ler, fontlar, video); ekran altı medyayı geç yükleyin.",
        "Total transferred bytes in a fresh lab run drop below 3 MiB.",
        "Yeni bir lab ölçümünde toplam aktarılan bayt 3 MiB'nin altına iner.",
        "Total page weight and the largest resource in the next audit.",
        "Sonraki denetimde toplam sayfa ağırlığı ve en büyük kaynak.",
    ),
    "too-many-requests": (
        "The page makes more than 100 network requests. This limit is a heuristic.",
        "Sayfa 100'den fazla ağ isteği yapıyor. Bu sınır bir sezgidir.",
        "Bundle and defer scripts and styles, inline tiny assets, drop unused third-party tags.",
        "Script ve stilleri birleştirip erteleyin, küçük varlıkları satır içine alın, kullanılmayan üçüncü taraf etiketlerini kaldırın.",
        "The request count in a fresh lab run is 100 or fewer.",
        "Yeni bir lab ölçümünde istek sayısı 100 veya altındadır.",
        "Request count per page in the next audit.",
        "Sonraki denetimde sayfa başına istek sayısı.",
    ),
    "uncompressed-text-resources": (
        "Text resources (HTML, CSS, JavaScript, JSON) larger than 1 KiB are served without compression.",
        "1 KiB'den büyük metin kaynakları (HTML, CSS, JavaScript, JSON) sıkıştırmasız sunuluyor.",
        "Enable gzip or Brotli on the server or CDN for text responses.",
        "Sunucuda veya CDN'de metin yanıtları için gzip veya Brotli'yi etkinleştirin.",
        "The listed resources answer with a content-encoding header in a fresh fetch.",
        "Listelenen kaynaklar yeni bir istekte content-encoding başlığıyla yanıt verir.",
        "Transferred bytes of text resources in the next audit.",
        "Sonraki denetimde metin kaynaklarının aktarılan baytı.",
    ),
    "static-assets-no-cache": (
        "Several static files (scripts, styles, images, fonts) are cacheable for less than one day or not at all.",
        "Birkaç statik dosya (script, stil, görsel, font) bir günden kısa süre veya hiç önbelleğe alınamıyor.",
        "Send Cache-Control with a long max-age for fingerprinted static files.",
        "Parmak izli statik dosyalar için uzun max-age'li Cache-Control gönderin.",
        "The listed files answer with a max-age of at least one day.",
        "Listelenen dosyalar en az bir günlük max-age ile yanıt verir.",
        "Repeat-visit transfer size in the next audit.",
        "Sonraki denetimde tekrar ziyaret aktarım boyutu.",
    ),
    "render-blocking-resources": (
        "Four or more stylesheets or scripts block the first paint. This count is a heuristic.",
        "Dört veya daha fazla stil dosyası ya da script ilk boyamayı engelliyor. Bu sayı bir sezgidir.",
        "Defer or async non-critical scripts and inline the critical CSS.",
        "Kritik olmayan script'leri defer/async yapın ve kritik CSS'i satır içine alın.",
        "The number of render-blocking resources drops below four in a fresh lab run.",
        "Yeni bir lab ölçümünde render engelleyen kaynak sayısı dörde düşer.",
        "First Contentful Paint in the next audit.",
        "Sonraki denetimde First Contentful Paint.",
    ),
    "third-party-heavy": (
        "Third-party hosts account for a large share of the requests or bytes. This is a heuristic.",
        "Üçüncü taraf alan adları isteklerin veya baytların büyük bölümünü oluşturuyor. Bu bir sezgidir.",
        "Review each third-party tag; remove what is unused and load the rest after the main content.",
        "Her üçüncü taraf etiketini gözden geçirin; kullanılmayanı kaldırın, kalanını ana içerikten sonra yükleyin.",
        "The third-party share falls below the threshold in a fresh lab run.",
        "Yeni bir lab ölçümünde üçüncü taraf payı eşiğin altına iner.",
        "Third-party requests and bytes in the next audit.",
        "Sonraki denetimde üçüncü taraf istek ve bayt sayısı.",
    ),
    "mobile-horizontal-scroll": (
        "On a phone-sized screen the page is wider than the screen, so it scrolls sideways.",
        "Telefon boyutlu ekranda sayfa ekrandan geniş, yani yana kayıyor.",
        "Find the element wider than the viewport and make it responsive (max-width: 100%).",
        "Görünüm alanından geniş öğeyi bulup duyarlı yapın (max-width: 100%).",
        "The mobile lab run reports no horizontal overflow.",
        "Mobil lab ölçümünde yatay taşma görünmez.",
        "Mobile layout check in the next audit.",
        "Sonraki denetimde mobil yerleşim kontrolü.",
    ),
    "mobile-tap-targets-small": (
        "Several tap targets are smaller than 24 by 24 CSS pixels (WCAG 2.2 AA). The count threshold is a heuristic.",
        "Birkaç dokunma hedefi 24x24 CSS pikselden küçük (WCAG 2.2 AA). Sayı eşiği bir sezgidir.",
        "Enlarge buttons and links to at least 24 px, ideally 48 px, or add spacing around them.",
        "Düğme ve bağlantıları en az 24 px, mümkünse 48 px yapın veya çevrelerine boşluk ekleyin.",
        "The mobile lab run finds fewer than three undersized tap targets.",
        "Mobil lab ölçümünde üçten az küçük dokunma hedefi bulunur.",
        "Number of small tap targets in the next audit.",
        "Sonraki denetimde küçük dokunma hedefi sayısı.",
    ),
    "mobile-font-too-small": (
        "A large share of the text is set below 12 px on a phone. This share is a heuristic.",
        "Metnin büyük bölümü telefonda 12 px'in altında. Bu pay bir sezgidir.",
        "Use a base font size of about 16 px and avoid text below 12 px.",
        "Yaklaşık 16 px temel yazı boyutu kullanın, 12 px altı metinden kaçının.",
        "The share of text below 12 px drops under 20% in the mobile lab run.",
        "12 px altı metin payı mobil lab ölçümünde %20'nin altına düşer.",
        "Small-text share in the next audit.",
        "Sonraki denetimde küçük metin payı.",
    ),
    "image-too-large": (
        "Some images are larger than the size guideline for their kind (thumbnail 100 KB, content 200 KB, hero 300 KB).",
        "Bazı görseller türleri için boyut rehberinden büyük (küçük resim 100 KB, içerik 200 KB, hero 300 KB).",
        "Compress the listed images, or serve a smaller size with srcset.",
        "Listelenen görselleri sıkıştırın veya srcset ile daha küçük boyut sunun.",
        "The listed images are below the guideline in a fresh lab run.",
        "Listelenen görseller yeni bir lab ölçümünde rehberin altındadır.",
        "Total image bytes in the next audit.",
        "Sonraki denetimde toplam görsel baytı.",
    ),
    "image-critically-large": (
        "Some images are far larger than the size guideline for their kind (thumbnail 200 KB, content 500 KB, hero 700 KB).",
        "Bazı görseller türleri için boyut rehberinden çok daha büyük (küçük resim 200 KB, içerik 500 KB, hero 700 KB).",
        "Resize and compress these images first, and prefer WebP or AVIF.",
        "Önce bu görselleri yeniden boyutlandırıp sıkıştırın, WebP veya AVIF tercih edin.",
        "The listed images drop below 500 KB (content) in a fresh lab run.",
        "Listelenen görseller yeni bir lab ölçümünde 500 KB'nin (içerik) altına iner.",
        "Largest image size in the next audit.",
        "Sonraki denetimde en büyük görsel boyutu.",
    ),
    "image-oversized-for-display": (
        "Some images are much larger (in pixels) than the space they are shown in. This is a heuristic.",
        "Bazı görseller gösterildikleri alandan (piksel olarak) çok daha büyük. Bu bir sezgidir.",
        "Serve the image at the displayed size (with srcset for sharper screens).",
        "Görseli gösterildiği boyutta sunun (daha keskin ekranlar için srcset ile).",
        "The listed images are at most about twice the displayed size.",
        "Listelenen görseller gösterilen boyutun en fazla yaklaşık iki katıdır.",
        "Image pixels versus displayed pixels in the next audit.",
        "Sonraki denetimde görsel pikselleri ile gösterilen pikseller.",
    ),
    "image-legacy-format": (
        "Some large images are served as JPEG or PNG. WebP or AVIF is usually smaller. This is a heuristic.",
        "Bazı büyük görseller JPEG veya PNG olarak sunuluyor. WebP veya AVIF genellikle daha küçüktür. Bu bir sezgidir.",
        "Serve WebP or AVIF (with a JPEG fallback in a picture element if needed).",
        "WebP veya AVIF sunun (gerekirse picture öğesinde JPEG yedeğiyle).",
        "The listed images are served as WebP or AVIF in a fresh fetch.",
        "Listelenen görseller yeni bir istekte WebP veya AVIF olarak sunulur.",
        "Share of images served in modern formats in the next audit.",
        "Sonraki denetimde modern formatta sunulan görsel payı.",
    ),
}

_entries: dict[str, dict[str, str]] = {}
for _id, (f_en, f_tr, r_en, r_tr, k_en, k_tr, l_en, l_tr) in _MSG.items():
    _entries[f"finding.{_id}"] = {"en": f_en, "tr": f_tr}
    _entries[f"rec.{_id}"] = {"en": r_en, "tr": r_tr}
    _entries[f"fail.{_id}"] = {"en": k_en, "tr": k_tr}
    _entries[f"lead.{_id}"] = {"en": l_en, "tr": l_tr}
register_messages(_entries)

assert set(_MSG) == {d.id for d in rules_perf.PERF_RULES}
