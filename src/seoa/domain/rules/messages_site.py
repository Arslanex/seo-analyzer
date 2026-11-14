"""EN + TR texts for the site-level rules (fixed text; never contains page data)."""

from __future__ import annotations

from seoa.domain.rules.registry import register_messages

# id -> (finding EN, finding TR, recommendation EN, recommendation TR)
_MSG: dict[str, tuple[str, str, str, str]] = {
    "tls-handshake-failed": (
        "The TLS handshake with the site did not complete.",
        "Siteyle TLS el sıkışması tamamlanamadı.",
        "Make sure the server speaks TLS 1.2 or newer, presents a complete certificate chain and answers the correct host name (SNI).",
        "Sunucunun TLS 1.2 veya üstünü konuştuğundan, eksiksiz bir sertifika zinciri sunduğundan ve doğru alan adına (SNI) yanıt verdiğinden emin olun.",
    ),
    "tls-cert-expired": (
        "The TLS certificate has expired.",
        "TLS sertifikasının süresi dolmuş.",
        "Renew the certificate now and automate renewal so it cannot lapse again.",
        "Sertifikayı hemen yenileyin ve tekrar süresi dolmasın diye yenilemeyi otomatikleştirin.",
    ),
    "tls-cert-not-yet-valid": (
        "The TLS certificate is not valid yet.",
        "TLS sertifikası henüz geçerli değil.",
        "Check the certificate's start date and the server clock; install a certificate that is valid now.",
        "Sertifikanın başlangıç tarihini ve sunucu saatini kontrol edin; şu an geçerli bir sertifika yükleyin.",
    ),
    "tls-cert-hostname-mismatch": (
        "The TLS certificate does not cover the requested host.",
        "TLS sertifikası istenen alan adını kapsamıyor.",
        "Issue a certificate whose names include this host (and its www or non-www counterpart).",
        "Bu alan adını (ve www / www'suz karşılığını) içeren bir sertifika alın.",
    ),
    "tls-cert-not-trusted": (
        "The certificate chain did not verify against the system trust store.",
        "Sertifika zinciri sistem güven deposuna karşı doğrulanamadı.",
        "Serve the full chain including intermediate certificates and use a certificate from a public authority.",
        "Ara sertifikalar dahil tam zinciri sunun ve herkese açık bir otoriteden alınmış sertifika kullanın.",
    ),
    "tls-cert-expiring-soon": (
        "The TLS certificate expires within 14 days.",
        "TLS sertifikasının süresi 14 gün içinde doluyor.",
        "Renew the certificate before it expires and set up automatic renewal.",
        "Sertifikayı süresi dolmadan yenileyin ve otomatik yenilemeyi kurun.",
    ),
    "tls-old-protocol": (
        "The server negotiated a TLS version older than 1.2.",
        "Sunucu 1.2'den eski bir TLS sürümü üzerinde anlaştı.",
        "Disable TLS 1.0 and 1.1 on the server.",
        "Sunucuda TLS 1.0 ve 1.1'i kapatın.",
    ),
    "tls-sibling-not-covered": (
        "The www or non-www counterpart fails its HTTPS request with a certificate or TLS error, and this host's certificate does not cover it.",
        "www veya www'suz karşılık sertifika ya da TLS hatasıyla başarısız oluyor ve bu alan adının sertifikası onu kapsamıyor.",
        "Add the counterpart host to the certificate or make it redirect without a certificate error.",
        "Karşılık alan adını sertifikaya ekleyin ya da sertifika hatası vermeden yönlendirin.",
    ),
    "http-no-https-redirect": (
        "The http:// address does not redirect to https://.",
        "http:// adresi https:// adresine yönlendirmiyor.",
        "Redirect all http:// requests to https:// with a 301 on the same host.",
        "Tüm http:// isteklerini aynı alan adında 301 ile https:// adresine yönlendirin.",
    ),
    "http-https-redirect-chain": (
        "The http:// address reaches https:// only after more than one redirect.",
        "http:// adresi https:// adresine birden fazla yönlendirmeden sonra ulaşıyor.",
        "Redirect http:// straight to the final https:// URL in one hop.",
        "http:// adresini tek adımda nihai https:// adresine yönlendirin.",
    ),
    "http-https-redirect-temporary": (
        "The http to https redirect is temporary, not a 301 or 308.",
        "http'den https'e yönlendirme kalıcı (301/308) değil, geçici.",
        "Use a permanent redirect (301 or 308) from http to https.",
        "http'den https'e kalıcı yönlendirme (301 veya 308) kullanın.",
    ),
    "www-not-consolidated": (
        "The www and non-www hosts end on different URLs.",
        "www ve www'suz adresler farklı URL'lerde sonlanıyor.",
        "Pick one preferred host and redirect the other to it with a 301.",
        "Tercih edilen tek bir alan adı seçin ve diğerini 301 ile ona yönlendirin.",
    ),
    "www-sibling-unreachable": (
        "The www or non-www counterpart of the host did not answer.",
        "Alan adının www veya www'suz karşılığı yanıt vermedi.",
        "If the counterpart should work, add DNS and a redirect to the preferred host; otherwise no action is needed.",
        "Karşılık adres çalışmalıysa DNS kaydı ekleyip tercih edilen alan adına yönlendirin; aksi halde işlem gerekmez.",
    ),
    "hsts-missing": (
        "The HTTPS response does not send a Strict-Transport-Security header.",
        "HTTPS yanıtı Strict-Transport-Security başlığı göndermiyor.",
        "Send Strict-Transport-Security with max-age of at least one year once all subdomains serve HTTPS.",
        "Tüm alt alan adları HTTPS sunduktan sonra en az bir yıl max-age ile Strict-Transport-Security gönderin.",
    ),
    "hsts-disabled": (
        "The Strict-Transport-Security header has no effect because max-age is missing or zero.",
        "Strict-Transport-Security başlığı, max-age eksik veya sıfır olduğu için etkisiz.",
        "Set a positive max-age (31536000 or more).",
        "Pozitif bir max-age (31536000 veya üzeri) ayarlayın.",
    ),
    "hsts-weak": (
        "The Strict-Transport-Security header is weak.",
        "Strict-Transport-Security başlığı zayıf.",
        "Use max-age of at least one year and add includeSubDomains if every subdomain serves HTTPS.",
        "En az bir yıllık max-age kullanın ve tüm alt alan adları HTTPS sunuyorsa includeSubDomains ekleyin.",
    ),
    "csp-missing": (
        "No Content-Security-Policy header is sent.",
        "Content-Security-Policy başlığı gönderilmiyor.",
        "Introduce a Content-Security-Policy, starting in report-only mode.",
        "Önce yalnızca rapor modunda olmak üzere bir Content-Security-Policy tanımlayın.",
    ),
    "csp-report-only": (
        "The Content-Security-Policy is report-only, so nothing is enforced.",
        "Content-Security-Policy yalnızca rapor modunda, yani hiçbir şey zorlanmıyor.",
        "Move the policy from report-only to enforced once the reports are clean.",
        "Raporlar temizlendiğinde politikayı rapor modundan zorlayıcı moda alın.",
    ),
    "csp-weak": (
        "The Content-Security-Policy has obvious gaps.",
        "Content-Security-Policy'de belirgin boşluklar var.",
        "Remove unsafe-inline/unsafe-eval and wildcard script sources; add object-src and base-uri.",
        "unsafe-inline/unsafe-eval ve joker script kaynaklarını kaldırın; object-src ve base-uri ekleyin.",
    ),
    "nosniff-missing": (
        "X-Content-Type-Options is not set to nosniff.",
        "X-Content-Type-Options 'nosniff' olarak ayarlı değil.",
        "Send X-Content-Type-Options: nosniff.",
        "X-Content-Type-Options: nosniff gönderin.",
    ),
    "clickjacking-protection-missing": (
        "Neither X-Frame-Options nor a CSP frame-ancestors directive limits framing of the page.",
        "Ne X-Frame-Options ne de CSP frame-ancestors sayfanın çerçevelenmesini sınırlıyor.",
        "Send X-Frame-Options (DENY or SAMEORIGIN) or a CSP frame-ancestors directive.",
        "X-Frame-Options (DENY veya SAMEORIGIN) ya da CSP frame-ancestors yönergesi gönderin.",
    ),
    "referrer-policy-missing": (
        "No Referrer-Policy header is sent, so the browser default applies.",
        "Referrer-Policy başlığı gönderilmiyor, tarayıcı varsayılanı geçerli.",
        "Send Referrer-Policy: strict-origin-when-cross-origin (or stricter).",
        "Referrer-Policy: strict-origin-when-cross-origin (veya daha katı) gönderin.",
    ),
    "referrer-policy-unsafe": (
        "The Referrer-Policy is unsafe-url or not a recognised value.",
        "Referrer-Policy unsafe-url veya tanınmayan bir değer.",
        "Use a recognised, safer value such as strict-origin-when-cross-origin.",
        "strict-origin-when-cross-origin gibi tanınan ve daha güvenli bir değer kullanın.",
    ),
    "permissions-policy-missing": (
        "No Permissions-Policy header is sent.",
        "Permissions-Policy başlığı gönderilmiyor.",
        "Send a Permissions-Policy that disables browser features the site does not use.",
        "Sitenin kullanmadığı tarayıcı özelliklerini kapatan bir Permissions-Policy gönderin.",
    ),
    "cookie-missing-secure": (
        "One or more cookies are set without the Secure flag.",
        "Bir veya daha fazla çerez Secure bayrağı olmadan ayarlanıyor.",
        "Add the Secure attribute to cookies on an HTTPS site.",
        "HTTPS sitesindeki çerezlere Secure özniteliğini ekleyin.",
    ),
    "cookie-missing-httponly": (
        "One or more cookies are readable by scripts because HttpOnly is not set.",
        "HttpOnly ayarlı olmadığı için bir veya daha fazla çerez betiklerle okunabiliyor.",
        "Add HttpOnly to cookies that scripts do not need to read.",
        "Betiklerin okumasına gerek olmayan çerezlere HttpOnly ekleyin.",
    ),
    "cookie-missing-samesite": (
        "One or more cookies set no SameSite attribute.",
        "Bir veya daha fazla çerez SameSite özniteliği belirtmiyor.",
        "Set SameSite=Lax or Strict explicitly on cookies.",
        "Çerezlerde SameSite=Lax veya Strict değerini açıkça belirtin.",
    ),
    "robots-missing": (
        "No robots.txt file was found (the server answered with a 4xx status), so no crawl restrictions apply.",
        "robots.txt bulunamadı (sunucu 4xx döndürdü), bu yüzden tarama kısıtı uygulanmıyor.",
        "Publish a robots.txt that lists your sitemap(s) and any paths crawlers should avoid.",
        "Site haritanızı ve tarayıcıların girmemesi gereken yolları listeleyen bir robots.txt yayınlayın.",
    ),
    "robots-unreachable": (
        "robots.txt could not be fetched (server error or no response); crawlers may treat the whole site as disallowed meanwhile.",
        "robots.txt alınamadı (sunucu hatası veya yanıt yok); bu sürede tarayıcılar tüm siteyi yasaklı sayabilir.",
        "Fix the server error on /robots.txt; it must answer 200 or a 4xx status, never 5xx.",
        "/robots.txt üzerindeki sunucu hatasını giderin; 200 veya 4xx dönmeli, asla 5xx değil.",
    ),
    "robots-blocks-site": (
        "robots.txt disallows the whole site for crawlers.",
        "robots.txt tüm siteyi tarayıcılara yasaklıyor.",
        "Remove 'Disallow: /' for the user agents that should crawl the site.",
        "Siteyi taraması gereken kullanıcı ajanları için 'Disallow: /' satırını kaldırın.",
    ),
    "robots-disallows-entry": (
        "robots.txt disallows the audited page for a crawler.",
        "robots.txt denetlenen sayfayı bir tarayıcı için yasaklıyor.",
        "Allow the page in robots.txt if it should be crawled and indexed.",
        "Sayfa taranıp dizinlenecekse robots.txt'te izin verin.",
    ),
    "ai-search-bots-blocked": (
        "robots.txt blocks at least one AI search crawler at the site root.",
        "robots.txt en az bir yapay zekâ arama tarayıcısını site kökünde engelliyor.",
        "If you want to appear in that AI engine's answers, allow its search crawler; blocking it removes the site from that engine.",
        "O yapay zekâ motorunun yanıtlarında yer almak istiyorsanız arama tarayıcısına izin verin; engellemek siteyi o motordan çıkarır.",
    ),
    "ai-training-bots-blocked": (
        "robots.txt blocks AI training crawlers or training control tokens (informational).",
        "robots.txt yapay zekâ eğitim tarayıcılarını veya eğitim kontrol belirteçlerini engelliyor (bilgi).",
        "No action is needed if this is intended; training bots are separate from search crawlers.",
        "Bilinçli bir tercihse işlem gerekmez; eğitim botları arama tarayıcılarından ayrıdır.",
    ),
    "llms-txt-missing": (
        "No /llms.txt file was found. It is an optional community proposal that Google Search ignores.",
        "/llms.txt dosyası bulunamadı. Bu, Google Arama'nın yok saydığı isteğe bağlı bir topluluk önerisidir.",
        "Optional: publish /llms.txt if you want to guide AI agents; it has no effect on Google Search.",
        "İsteğe bağlı: yapay zekâ ajanlarına yol göstermek istiyorsanız /llms.txt yayınlayın; Google Arama'ya etkisi yoktur.",
    ),
    "sitemap-missing": (
        "No XML sitemap was found in robots.txt or at the common locations.",
        "robots.txt'te veya yaygın konumlarda XML site haritası bulunamadı.",
        "Publish an XML sitemap and reference it from robots.txt.",
        "Bir XML site haritası yayınlayın ve robots.txt'ten referans verin.",
    ),
    "sitemap-invalid": (
        "A sitemap could not be read (invalid XML, DOCTYPE, empty, unsupported format, bad gzip or an error status).",
        "Bir site haritası okunamadı (geçersiz XML, DOCTYPE, boş, desteklenmeyen biçim, bozuk gzip veya hata durumu).",
        "Serve a well-formed sitemap (urlset or sitemapindex) without a DOCTYPE and with a 200 status.",
        "DOCTYPE içermeyen, 200 durumlu, düzgün biçimli bir site haritası (urlset veya sitemapindex) sunun.",
    ),
    "sitemap-too-large": (
        "A sitemap exceeds the protocol limits (50,000 URLs or 50 MiB uncompressed).",
        "Bir site haritası protokol sınırlarını aşıyor (50.000 URL veya sıkıştırılmamış 50 MiB).",
        "Split the sitemap into several files listed in a sitemap index.",
        "Site haritasını bir site haritası dizininde listelenen birkaç dosyaya bölün.",
    ),
    "sitemap-nested-index": (
        "A sitemap index lists another sitemap index (nesting is not allowed by the protocol).",
        "Bir site haritası dizini başka bir dizini listeliyor (protokol iç içe dizine izin vermez).",
        "List only sitemap files in a sitemap index.",
        "Site haritası dizininde yalnızca site haritası dosyalarını listeleyin.",
    ),
    "sitemap-invalid-urls": (
        "Some sitemap entries are not valid absolute http(s) URLs or are too long.",
        "Bazı site haritası girdileri geçerli mutlak http(s) URL'si değil veya çok uzun.",
        "Use absolute http(s) URLs shorter than 2,048 characters.",
        "2.048 karakterden kısa, mutlak http(s) URL'leri kullanın.",
    ),
    "sitemap-cross-host-urls": (
        "The sitemap lists URLs on a different host than the sitemap file.",
        "Site haritası, dosyadan farklı bir alan adındaki URL'leri listeliyor.",
        "List only URLs of the host that serves the sitemap, or submit cross-host sitemaps through robots.txt.",
        "Yalnızca site haritasını sunan alan adının URL'lerini listeleyin veya alanlar arası haritaları robots.txt ile bildirin.",
    ),
    "sitemap-duplicate-urls": (
        "The same URL is listed more than once in the sitemap files.",
        "Aynı URL site haritası dosyalarında birden fazla kez listelenmiş.",
        "List each URL once.",
        "Her URL'yi yalnızca bir kez listeleyin.",
    ),
    "sitemap-lastmod-invalid": (
        "Some lastmod values are not valid W3C datetimes.",
        "Bazı lastmod değerleri geçerli W3C tarih-saat biçiminde değil.",
        "Write lastmod as YYYY-MM-DD or a full W3C datetime.",
        "lastmod değerini YYYY-AA-GG veya tam W3C tarih-saat biçiminde yazın.",
    ),
    "sitemap-lastmod-uniform": (
        "Nearly all lastmod values in the sitemap are identical, which makes them useless as a change signal (heuristic).",
        "Site haritasındaki lastmod değerlerinin neredeyse tamamı aynı; bu, değişiklik sinyali olarak işe yaramaz (sezgisel).",
        "Set lastmod to the real last modification time of each page, or omit it.",
        "lastmod'u her sayfanın gerçek son değişiklik zamanına ayarlayın veya hiç yazmayın.",
    ),
    "sitemap-child-unreachable": (
        "Some child sitemaps listed in a sitemap index could not be fetched.",
        "Bir site haritası dizininde listelenen bazı alt haritalar alınamadı.",
        "Make sure every sitemap listed in the index answers with 200.",
        "Dizinde listelenen her site haritasının 200 döndüğünden emin olun.",
    ),
}

# group templates for the failure check / leading indicator (rule-specific text is the finding+rec)
_GROUPS: tuple[tuple[tuple[str, ...], tuple[str, str], tuple[str, str]], ...] = (
    (
        ("tls-", "http-", "www-"),
        (
            "A fresh audit still reports this finding for the host.",
            "Yeni bir denetim bu bulguyu alan adı için hâlâ raporluyor.",
        ),
        (
            "Certificate expiry date and redirect status in your uptime monitoring.",
            "Çalışma zamanı izlemenizdeki sertifika bitiş tarihi ve yönlendirme durumu.",
        ),
    ),
    (
        ("hsts-", "csp-", "nosniff-", "clickjacking-", "referrer-", "permissions-", "cookie-"),
        (
            "The response header is still missing or unchanged in a fresh fetch of the page.",
            "Sayfanın yeni bir isteğinde yanıt başlığı hâlâ eksik veya değişmemiş.",
        ),
        (
            "The header value in a response header scanner (a security header check) after deployment.",
            "Dağıtımdan sonra yanıt başlığı tarayıcısındaki (güvenlik başlığı kontrolü) başlık değeri.",
        ),
    ),
    (
        ("robots-", "ai-", "llms-"),
        (
            "A fresh fetch of /robots.txt still shows the same rule or status.",
            "/robots.txt'in yeni bir isteği hâlâ aynı kuralı veya durumu gösteriyor.",
        ),
        (
            "Crawl statistics (pages crawled per day) in Google Search Console or server logs.",
            "Google Search Console veya sunucu günlüklerindeki tarama istatistikleri (günlük taranan sayfa).",
        ),
    ),
    (
        ("sitemap-",),
        (
            "A fresh audit still reports this sitemap finding.",
            "Yeni bir denetim bu site haritası bulgusunu hâlâ raporluyor.",
        ),
        (
            "Submitted vs. indexed URL counts in the Sitemaps report of Google Search Console.",
            "Google Search Console Site Haritaları raporundaki gönderilen ve dizinlenen URL sayıları.",
        ),
    ),
)


def _register() -> None:
    entries: dict[str, dict[str, str]] = {}
    for rid, (m_en, m_tr, r_en, r_tr) in _MSG.items():
        entries[f"finding.{rid}"] = {"en": m_en, "tr": m_tr}
        entries[f"rec.{rid}"] = {"en": r_en, "tr": r_tr}
        for prefixes, fail, lead in _GROUPS:
            if rid.startswith(prefixes):
                entries[f"fail.{rid}"] = {"en": fail[0], "tr": fail[1]}
                entries[f"lead.{rid}"] = {"en": lead[0], "tr": lead[1]}
                break
    register_messages(entries)


_register()
MESSAGE_RULE_IDS = tuple(_MSG)
