# 05. Sistem Tasarımı

**Bölüm I:** Veri toplama alt sistemi (güvenli fetch, render, keşif, örneklem) · **Bölüm II:** Genel sistem (bileşenler, güven bölgeleri, tehdit modeli, dağıtım)

> Durum: **Taslak v0.3** (D9: **Python**; D7 katmana bağlı uzlaştırıldı; Bölüm II genel sistem tasarımı eklendi) · Önceki belge: [`01-evaluation-system.md`](01-evaluation-system.md)
> İşaretler: `[K]` kaynak projeden alındı · `[B]` bizim kararımız · `[?]` açık karar · `[doğrulandı]` kaynak kodla kontrol edildi
> Teknoloji yığını **Python ≥ 3.11** (kaynakla aynı: `pyproject.toml requires-python = ">=3.11"`). Kaynak script'ler büyük oranda doğrudan taşınabilir; tek ciddi istisna DNS pin yöntemidir (§5.2). Kapsam kaybı analizi: [`00-capability-parity.md`](00-capability-parity.md).

---

## 1. Bu belgenin görevi

Belge 01, değerlendirme katmanının **ne ölçeceğini** tanımladı. Bu belge, ölçümün girdisini üretir: hangi URL'ler, hangi güvenlik kurallarıyla, hangi sınırlarla çekilir; hangileri render edilir; kaç sayfa örneklenir.

Bu katmanın 01'e verdiği sözleşme:

| 01'deki kavram | Bu belgede nasıl beslenir |
|---|---|
| `requires: ["headers","rendered","psi","robots","sitemap"]` | Her bir kaynağın "mevcut / yok / başarısız" durumu (§12) |
| `not_checked[{id, reason}]` | Fetch/render hatalarının gerekçe kodları (§12) |
| Kapsam % (§8.4) | `pages_crawled / pages_planned` ve kaynak erişilebilirliği |
| Kapı (§8.3) | Ana URL durum kodu, TLS, robots engeli |
| Güven (§8.5) | Örneklem büyüklüğü, render başarısı |
| `js_gap` | Ham vs render karşılaştırması (§7) |

## 2. Kaynakta ne var, ne yok (doğrulama)

Tasarıma başlamadan önce kaynak kodu kontrol ettim. En önemli bulgu: **kaynak projede gerçek bir crawler yoktur.**

| Konu | Kaynak durumu | Kanıt |
|---|---|---|
| Crawl kuralları (500 sayfa, 5 eşzamanlı, 1 sn gecikme, 3 redirect) | **Yalnızca prompt metni** | `skills/seo-audit/SKILL.md` "Crawl Configuration". `scripts/` altında crawl kuyruğu/frontier yok `[doğrulandı]` |
| robots.txt'e uyma (`can_fetch`) | **Kodda yok** | `robotparser`/`can_fetch` hiçbir script'te geçmiyor. Yalnızca `agentic_check.py` robots'u RFC 9309 grup seçimiyle ayrıştırır (AI botları için) `[doğrulandı]` |
| 429 / Retry-After / retry | **Kodda yok** | `fetch_page.py`, `url_safety.py`, `sitemap_discovery.py` içinde eşleşme yok `[doğrulandı]` |
| Redirect sınırı | Kodda **5** (SKILL.md 3 diyor) | `fetch_page.py:113 max_redirects=5` `[doğrulandı, çelişki]` |
| Sayfa başına zaman aşımı | `fetch_page` 30 sn; `render_page` 15 000 ms | `--timeout` varsayılanı 30; `render_page(timeout_ms=15000)` `[doğrulandı]` |
| SSRF koruması | **Güçlü ve kodda** | `url_safety.py` (1442 satır) |
| Sitemap keşfi | **Kodda, sınırlı ve güvenli** | `sitemap_discovery.py` |
| Render / SPA tespiti | **Kodda** | `render_page._is_spa`, `js_gap` |
| Tam site crawl | Opsiyonel **Firecrawl extension** (ücretli MCP) | `extensions/firecrawl/` |

Sonuç: SSRF, sitemap, kodlama ve render mantığını kaynaktan alıyoruz. **Crawl frontier, robots uyumu, rate limit ve retry'ı sıfırdan tasarlıyoruz** `[B]`. Bu belgenin en çok ürün kararı içeren kısmı budur.

## 3. Genel akış

```
Kullanıcı girişi ("example.com")
   │
   ▼
[1] Giriş normalizasyonu ───────────── geçersiz → hata (skor yok)
   │
   ▼
[2] SSRF ön doğrulama (DNS çöz + her kaydı kontrol et + pin) ── reddedildi → hata
   │
   ▼
[3] Ana URL fetch (limitli, redirect manuel) ── ulaşılamaz → hata raporu
   │          └→ transport: TLS + header + http→https
   ▼
[4] robots.txt fetch + ayrıştırma (RFC 9309)
   │
   ▼
[5] Render kararı: is_spa? ── evet → headless render → js_gap
   │
   ├── Sayfa modu: STOP → ölçüm katmanına (belge 01)
   │
   ▼  Site modu
[6] Keşif: sitemap(lar) + ana sayfa iç linkleri
   │
   ▼
[7] Normalize + tekilleştir + şablon kümeleme
   │
   ▼
[8] Örneklem seçimi (N sayfa, tabakalı)
   │
   ▼
[9] Sayfa fetch (nazik, paralel sınırlı) ── bazıları render
   │
   ▼
Ölçüm katmanı (belge 01) ← pages[], site_facts, not_checked[]
```

## 4. Giriş normalizasyonu

Kullanıcı `example.com`, `https://www.example.com/blog/` veya `HTTP://Example.com:443` yazabilir.

| Adım | Kural | Kaynak |
|---|---|---|
| 1 | Boşluk kırp; şema yoksa `https://` ekle | `[B]` |
| 2 | Yalnız `http`/`https`; başka şema reddedilir (`file:`, `ftp:`, `javascript:`) | `[K]` `validate_url_strict` |
| 3 | IDN → punycode; hostname küçük harf; sondaki nokta kaldırılır | `[K]` `normalize_hostname`, `page_checks._idna_host` |
| 4 | Authority karışıklığı reddedilir (`user@host`, ters eğik çizgi, sayısal IP biçimleri: ondalık/hex/sekizlik) | `[K]` `_reject_authority_confusion` |
| 5 | Tracking parametreleri (`utm_*`, `fbclid`, `gclid`, `msclkid`, `mc_*`) kaldırılır | `[K]` `page_checks._TRACKING_PARAM_RE` |
| 6 | Parça (`#...`) atılır | `[B]` |
| 7 | https denenir; **TLS/bağlantı hatasında** http'ye düşülür ve `https-unavailable` bulgusu üretilir | `[B]` |

**Site kapsamı (scope)** `[B]`: ana URL redirect'lerden sonra son origin'e (`host`) çözülür. Taranabilir küme: o host + onun `www`/apex karşılığı. Diğer alt alanlar (`blog.example.com`, `shop.example.com`) **dışarıda** kalır; bulunursa raporda "taranmadı" notu düşülür. Gerekçe: alt alanlar ayrı site sayılabilir, sahiplik belirsiz, maliyet tahmin edilemez.

## 5. SSRF ve güvenlik tasarımı

Bu, bir SaaS için sistemin en kritik güvenlik yüzeyidir: kullanıcı bir URL verir, **sunucumuz** o adrese gider.

### 5.1 Kaynaktan alınan politika `[K, doğrulandı]`

`url_safety.py` şunları yapar; politika dilden bağımsızdır ve aynen taşınır:

| Kontrol | Detay |
|---|---|
| Şema | Yalnız `http`/`https` |
| Engellenen hostname'ler | `localhost`, `ip6-localhost`, `metadata.google.internal`, `metadata.goog`, `metadata.azure.com`, `metadata.ec2.internal`, `metadata.oraclecloud.com`, `169.254.169.254`, `fd00:ec2::254` ve benzerleri |
| IP sınıfları | private, loopback, link-local, multicast, reserved, unspecified, **paylaşılan adres alanı `100.64.0.0/10`** (Tailscale/CGNAT), ek IPv6 aralıkları |
| IPv4-mapped IPv6 | `::ffff:127.0.0.1` içindeki IPv4 olarak değerlendirilir |
| IPv6 zone id | `fe80::1%eth0` reddedilir |
| DNS | **Her** A ve AAAA kaydı public olmalı; biri private ise reddedilir (rebinding yarışı) |
| DNS64 | A kaydı olan host'ta sentetik `64:ff9b::/96` AAAA atlanır (IPv4 pin'lenir) |
| DNS pin | Doğrulanan IP'ye bağlanılır; yeniden çözümleme yok |
| Redirect | Her hop'ta hedef yeniden doğrulanır; redirect gövdesi 64 KiB ile sınırlı |
| Cloud metadata | İzin listesinde olsa bile reddedilir |

### 5.2 Kaynaktan **almayacaklarımız** `[B]`

- **`LOCAL_TARGETS` izin listesi:** Kaynakta yerel/staging adresleri denetlemek için var. Çok kiracılı SaaS'ta **hiç sunulmaz**. Özel ağ hedefi her zaman reddedilir.
- **Global `socket.getaddrinfo` monkey-patch ile DNS pin (`url_safety._pin_dns`):** Kaynakta thread-güvenli değil (global yama + non-blocking kilit) `[doğrulandı: 05 raporu]`. Aynı süreçte eşzamanlı ikinci istek hata alır. Kaynak Python olduğu için bu kodu kopyalamak cazip ama **sunucuda kullanılamaz**: asenkron bir web servisinde yüzlerce eşzamanlı fetch olacak.

  **Python'da önerilen yöntem** `[B, prototiple doğrulanacak]`: `aiohttp.TCPConnector(resolver=SafeResolver())`. `SafeResolver`, `aiohttp.abc.AbstractResolver`'dan türer; her çözümlemede **tüm** A/AAAA kayıtlarını `is_safe_ip` ile kontrol eder ve yalnız doğrulanmış IP'yi döndürür. Böylece bağlantıyı kuran kod ile doğrulayan kod **aynı çözümlemedir**: doğrula-sonra-bağlan arasındaki rebinding yarışı kapanır ve redirect hedefleri de aynı yoldan geçer (her yeni bağlantı resolver'dan geçer). Global durum yok, kilit yok. TLS doğrulaması hostname üzerinden devam eder (SNI/sertifika adı bozulmaz). Alternatif: `httpx` + özel ağ backend'i (daha fazla iç API'ye bağımlı, tercih edilmez).

  > **P1 bulgusu (deneyle doğrulandı, `docs/prototypes/P1-safe-resolver.md`):** `aiohttp` bağlantıyı resolver'ın döndürdüğü IP'ye kurar ve `Host` başlığını korur (tasarımın varsayımı doğru). **Ama `aiohttp` IP-literal URL'lerde resolver'ı hiç çağırmaz**; `http://127.0.0.1:port/` resolver'a uğramadan başarıyla gitti. Bu yüzden `SafeResolver` **tek başına yetmez**: her istek ve **her redirect adımı** önce `policy.check_url` ile doğrulanır, redirect'ler elle izlenir (`allow_redirects=False`).

  Portlanan kısım yalnız **politikadır**: `is_safe_ip`, `_BLOCKED_HOSTNAMES`, authority-confusion reddi, DNS64 istisnası ve `normalize_hostname`. Kaynağın SSRF testleri (`test_url_safety.py`, `_ipv6.py`, `_port_pin.py`) politikayı belgeler, ama `socket.getaddrinfo` yamasına bağlı olduğu için **yeni resolver'a değişmeden uymaz** `[doğrulandı]`; politika vakaları (hangi adres reddedilir) çıkarılıp `SafeResolver` adaptörüne karşı yeniden yazılır. (`test_hostile_inputs.py` bir SSRF testi **değildir**.)

### 5.3 Render (Chromium) katmanında kalan risk `[K, doğrulandı]`

`SECURITY.md` açıkça yazar: Chromium DNS'i kendi süreci içinde çözer, Python katmanındaki pin buna ulaşmaz. `make_safe_playwright_route_handler` her alt kaynak isteğini yeniden doğrular, ama **kararlı bir rebinding saldırganı yarışı kazanabilir** (TOCTOU). Kaynak bunu "güvenilmeyen, yüksek yönlendirmeli sitelere çalıştırmayın" diye bir kullanıcı uyarısıyla bırakıyor. **SaaS'ta bu uyarı yeterli değildir**, çünkü hedefleri kullanıcı seçer.

> **Render bulgusu (deneyle doğrulandı, MVP inşası):** Chromium HTTP yönlendirmelerini **kendi ağ yığını içinde** izler; `page.route` yalnız ilk isteği görür, ara adımları görmez. Üç deneyle doğrulandı: `continue_()` ile 302 → `127.0.0.1` gizli sunucuya erişildi; doğrulanmış 3xx'i `fulfill` etsek bile sonraki adımlar yine kontrolsüz gitti. **Aynı açık kaynak kaynak proje render yolunda da var** (`make_safe_playwright_route_handler` yalnız route'u görür). Çözüm: her isteği `route.fetch(max_redirects=0)` ile **biz** yapıyoruz, ≤5 adımlık zinciri handler içinde izleyip her `Location`'ı politika ve DNS ile doğruluyor, Chromium'a yalnız son yanıtı veriyoruz (`src/seoa/render/browser.py`). Sınırlar: alt-istekler Playwright'ın Node tarafından yapılır (DNS orada çözülür), yalnız GET yönlendirme izler, DNS yarışı tamamen kapanmaz; ağ seviyesinde egress firewall yine gereklidir.

Bizim ek önlemlerimiz `[B]`:

| Katman | Önlem |
|---|---|
| Ağ | Render worker'ı **egress firewall / egress proxy** arkasında; özel aralıklara (RFC1918, link-local, metadata, `100.64.0.0/10`) ağ seviyesinde çıkış yasak. Uygulama içi kontrolden bağımsız son savunma |
| Süreç | Worker, sırlara ve iç servislere erişimi olmayan ayrı ağ/hesapta; tek kullanımlık tarayıcı bağlamı |
| Route handler | Kaynaktaki handler korunur: her alt istek doğrulanır, WebSocket engellenir (`_never_connect_web_socket`), service worker kapalı |
| Kaynak kısıtı | Süre, bellek, istek sayısı, indirilen bayt üst sınırı (§7.4) |
| Kısıt | Render yalnız gerektiğinde (§7.1) |

Bu ağ seviyesi önlem olmadan render özelliği **üretime çıkarılmaz** `[B]`.

### 5.4 Prompt injection ve güvenilmeyen içerik `[K]`
Çekilen her içerik güvenilmeyen veridir (belge 01, P7). Fetch katmanı yalnız yapılandırılmış alanlar üretir; ham HTML modele **doğrudan verilmez**.

## 6. Fetch sözleşmesi

### 6.1 Sınırlar `[K, doğrulandı]` ve bizim ekimiz `[B]`

| Sınır | Değer | Kaynak |
|---|---|---|
| Maksimum sayfa gövdesi | **10 MiB** | `url_safety.MAX_PAGE_BYTES` |
| Redirect gövdesi | 64 KiB | `MAX_REDIRECT_BODY_BYTES` |
| Maksimum redirect | **5** (kaynak kodu; SKILL.md'deki "3" prompt metnidir) | `fetch_page.py:113` |
| Zaman aşımı | 30 sn (HTTP), 15 sn (render) | `fetch_page`, `render_page` |
| Sıkıştırma bombası koruması | `read_bounded`: bayt sayacı, gzip için sınırlı açma | `url_safety.read_bounded*` |
| JSON derinliği | 256 | `MAX_JSON_DEPTH` |
| Toplam süre (duvar saati) `[B]` | Sayfa başına 45 sn tavan (yavaş damlatma / slowloris) | yeni |
| Kullanıcı başına denetim bütçesi `[B]` | İstek sayısı, toplam bayt, toplam süre (§9.5) | yeni |

### 6.2 İstek kimliği (User-Agent) `[B]`

Kaynakta varsayılan UA, Chrome taklit eden bir dizedir (`... Chrome/150.0.7871.114 Safari/537.36 KaynakProje/2.0`) ve ayrıca `--googlebot` ile **Googlebot UA'sı** gönderebilir `[doğrulandı]`. İkisini de değiştiriyoruz:

| Konu | Kararımız | Gerekçe |
|---|---|---|
| Kimlik | Açık ve tanımlanabilir bot: `SEOAnalyzerBot/1.0 (+https://<alan-adı>/bot)` | Site sahipleri günlükte bizi tanıyıp engelleyebilmeli; bot sayfası iletişim ve IP aralığı yayınlar |
| Googlebot taklidi | **Yok** | Üçüncü tarafın kimliğini taklit etmek etik ve hukuki risk; Google IP doğrulayan WAF'larda zaten başarısız olur ve yanlış sonuç üretir |
| Tarayıcı benzeri UA | Yalnız render'da `Chrome/... SEOAnalyzerBot/1.0` biçiminde, bot imzası sonda | Bazı siteler boş UA/bilinmeyen UA'ya kabuk HTML döner; kaynak da bunu belirtiyor |
| Dinamik render tespiti | Googlebot UA yerine **tek UA ile ham vs render farkı** (`js_gap`) | Prerender servisleriyle karşılaştırma kaynağın amacıydı; biz bunu kimlik taklidi olmadan yapabiliriz, sınırı raporda belirtiriz |
| `Accept-Language` | **Gönderilmez** `[K]` | Kaynak bilinçli göndermiyor: `en-US` göndermek çok dilli siteyi İngilizce'ye zorlar ve hreflang/yerelleştirme denetimini bozar `[doğrulandı]`. Türkçe odaklı olsak da aynı mantık geçerli |

Varsayılan başlıklar `[K]`: `Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8`, `Accept-Encoding: gzip, deflate`.

### 6.3 Kodlama çözme `[K, doğrulandı]`
Sıra: **BOM → `Content-Type` charset → `<meta>` ön tarama → utf-8**. Yanlış kodlama, Türkçe karakterlerde (`ı, ş, ğ, İ`) title/description uzunluğunu ve içerik analizini bozar; bu yüzden tam sırayı koruyoruz.

### 6.4 Redirect yönetimi `[B+K]`
- Redirect'ler **elle** izlenir (`redirect: 'manual'`), her hop SSRF kontrolünden geçer.
- Zincir kaydedilir: `redirect_chain[{url, status}]`. Kaynak yalnız URL listesi tutuyor (`response.history`); biz durum kodunu da saklıyoruz (301/302 ayrımı bulgu için gerekli).
- Döngü ve 5 hop üstü: `redirect-chain-too-long` bulgusu, ilk 5 hop'taki son URL analiz edilir.

### 6.5 Sayfa sonucu (çıktı sözleşmesi) `[B, fetch_page'den türetildi]`

```json
{
  "url": "https://example.com/a",
  "final_url": "https://example.com/a/",
  "status": 200,
  "redirect_chain": [{"url": "...", "status": 301}],
  "headers": {"content-type": "text/html; charset=utf-8", "x-robots-tag": null},
  "html_bytes": 48211,
  "content_encoding": "gzip",
  "timing": {"ttfb_ms": 212, "total_ms": 640},
  "html": "<…>",
  "rendered": null,
  "mode_used": "raw",
  "fetched_at": "2026-11-13T10:00:00Z",
  "error": null,
  "truncated": false
}
```

Alan adları kaynaktaki `fetch_page` sonucuyla uyumludur (`url`, `status_code`, `content`, `headers`, `redirect_chain`, `ttfb_ms`, `response_time_ms`, `content_bytes`, `error`) `[doğrulandı]`; `mode_used` `render_page` çıktısından gelir (`raw`/`rendered`).

## 7. Render politikası

### 7.1 Ne zaman render edilir `[K]`
`render_page` üç mod sunar: `auto` (varsayılan), `always`, `never`. `auto`'da önce ham HTTP çekilir, `_is_spa()` doğruysa Playwright devreye girer `[doğrulandı]`.

`_is_spa` sezgisi (aynen alınır):
1. Ham HTML yoksa → SPA.
2. Görünür metin **< 400 karakter** ve bilinen kabuk işaretlerinden biri varsa: `<div id="root"></div>`, `<div id="__next">`, `<div id="app"></div>`, `<div id="__nuxt">`, `data-svelte-h=`, `<astro-island `, "you need to enable javascript".
3. Görünür metin < 400 ve **aynı site oluşturucunun ≥ 2 işareti** (Wix, Webflow, Squarespace). Tek işaret yetmez, çünkü bu oluşturucular tam HTML de sunabilir.
4. `<body>` içinde görünür metin **< 100 karakter** (örnek: `example.com` ~125 karakter olduğu için eşik 100'de tutulmuş).

Yorum: sezgi bilerek **tutucudur**; gereksiz render pahalı olduğu için yanlış pozitif önlenmiştir. SSR sitelerde `__next` gibi işaretler kalır ama metin doludur, dolayısıyla render tetiklenmez.

### 7.2 `js_gap` (ham ve render farkı) `[K, doğrulandı]`
Hangi içeriğin yalnızca JavaScript sonrası var olduğunu ölçer. Eşikler:
- Görünür kelimelerin **%30'u** ve en az **25 kelime** yalnızca render sonrası varsa, **veya**
- Linklerin **%30'u** ve en az **3 link** yalnızca render sonrası varsa → boşluk var.

Ek olarak title, H1, canonical, schema tipleri ve robots direktifleri karşılaştırılır. Bu, **AI arama hazırlığı** kategorisinin (belge 01 §7.1) ana girdisidir: AI tarayıcıların çoğu JS çalıştırmaz.

### 7.3 Bizim render bütçemiz `[B]`

| Mod | Render edilen sayfalar |
|---|---|
| Sayfa analizi | O URL, yalnız `_is_spa` doğruysa |
| Site denetimi | Ana sayfa (her zaman `auto`) + **en fazla K=5** örneklenen sayfa (şablon başına bir temsilci) |
| Diğer sayfalar | Yalnız ham HTML |

Gerekçe: Chromium pahalıdır (bellek, süre, güvenlik yüzeyi). Şablon başına bir temsilci, `js_gap`'in şablon düzeyinde yaygın olup olmadığını gösterir.

### 7.4 Render kaynak sınırları `[B]`
15 sn zaman aşımı `[K]`; sayfa başına en çok 150 istek, 15 MiB indirme, 512 MiB bellek (tahmin, ölçülecek `[?]`); görüntü/font/medya engellenir (kaynakta `block_resources` var); tarayıcı havuzu, eşzamanlı render sayısı ≤ 2; her render yeni, izole bağlam.

### 7.5 Render çıktısından alınanlar `[K]`
`status_code`, `content` (render HTML), `raw_content`, `is_spa`, `extracted_text` (trafilatura; menü/altbilgi ayıklanmış), `publication_date`, JSON-LD (sınırlı: ≤50 blok, blok başına 256 KiB, toplam 1 MiB, 10 000 düğüm, derinlik 40), erişilebilirlik ağacı (isteğe bağlı, ≤10 000 düğüm). Erişilebilirlik ağacını MVP'de **almıyoruz** (yalnız ileride agentic kontrolleri için).

## 8. robots.txt politikası

### 8.1 Ayrıştırma `[K+B]`
Kaynakta robots ayrıştırması yalnız AI botu analizi için var ve RFC 9309 grup seçimini uygular: **adlandırılmış grup `*` grubunun yerini alır, miras yoktur** `[doğrulandı: agentic_check.parse_robots]`. Crawl izni için hazır kod yok. Bizim ayrıştırıcımız `[B]`:
- RFC 9309: grup seçimi, en uzun eşleşme kazanır, `Allow` eşitlikte kazanır, `*` ve `$` joker karakterleri.
- Boyut sınırı **1 MiB** `[K: MAX_ROBOTS_BYTES]`; fazlası kesilir (RFC 9309'a uygun).
- Durum kodu davranışı: 4xx → "kısıt yok"; 5xx/erişilemez → **geçici olarak tüm site engelli sayılır** (RFC 9309), sonra rapora `robots-unreachable` yazılır.
- Hazır bir paket (ör. `robots-parser`) kullanılabilir ama grup seçimi ve en uzun eşleşme davranışı **testle doğrulanmalıdır**, varsayılan davranışlarına güvenilmez.

### 8.2 Uyum kararı `[?] D8`

| Durum | Önerimiz |
|---|---|
| Kullanıcının verdiği **giriş URL'i** | Robots engellese bile **bir kez** çekilir (kullanıcı başlatmış tek istek; Lighthouse/PageSpeed gibi). Sonuç `robots-disallows-entry` bulgusuyla işaretlenir |
| Keşif ve örneklem sayfaları | **Robots'a uyulur**; engelli yollar çekilmez, `not_crawled: robots` olarak sayılır |
| Tüm site engelli (`Disallow: /`) | Yalnız giriş sayfası analiz edilir; kapı 70 (belge 01 §8.3); rapor bunu açıkça belirtir |
| Bot adımız (`SEOAnalyzerBot`) için özel kural | Uyulur |
| `Crawl-delay` | Saygı gösterilir, **10 sn ile sınırlı** (Google yok sayar; bizim için üst sınır nezaket/süre dengesi) `[B]` |

Neden giriş URL'i istisna: robots bir tarama yönergesidir, kullanıcının "bu sayfayı değerlendir" isteğini yasaklamaz; ama sistemin site genelinde sayfa toplaması farklıdır. Hukuki/ürün onayı gerekir.

## 9. Keşif ve örneklem

### 9.1 Keşif kaynakları (öncelik sırasıyla)

| # | Kaynak | Not |
|---|---|---|
| 1 | `robots.txt` içindeki `Sitemap:` satırları | `[K]` en çok **16** bildirilmiş sitemap (`MAX_DECLARED`) |
| 2 | Yaygın yollar | `/sitemap.xml`, `/sitemap_index.xml`, `/sitemap-index.xml`, `/wp-sitemap.xml` `[K]` |
| 3 | Ana sayfa iç linkleri | Derinlik 1 (yalnız ana sayfadan); aynı scope `[B]` |
| 4 | Giriş sayfasının iç linkleri | Sayfa modunda değil, yalnız site modunda |

### 9.2 Sitemap sınırları `[K, doğrulandı]`
Sitemap başına **50 MiB** (açılmış) ve **50 000 URL** protokol sınırı; index içinde en çok 50 çocuk sitemap (`DEFAULT_MAX_CHILDREN`); varsayılan örnek 20 URL (`DEFAULT_SAMPLE`); izlenen URL üst sınırı 2 milyon; `loc` en çok 2048 karakter; gzip sınırlı açılır; `lastmod` kalite kontrolü; RSS ve Atom beslemeleri de tanınır (`urlset`, `sitemapindex`, `rss`, `feed`). Kaynak, sitemap'e ait **parametre sırlarını maskeler** (`_SECRET_PARAM`).

Sitemap bulunamazsa bu bir **bulgu** (`sitemap-missing`) ve keşif yalnız ana sayfa linklerine düşer; `requires:["sitemap"]` olan kontroller `not_checked` olur.

### 9.3 URL normalizasyonu ve tekilleştirme `[K]`
`page_checks.canonicalize_url` ve `url_match_key` başlangıç alınır: IDN, yüzde-kaçış biçimi, tracking parametresi atma, büyük/küçük harf, çift eğik çizgi. İki URL aynı `url_match_key`'e sahipse tekildir. Ek `[B]`:
- Sorgu parametreli URL'ler: aynı yol için **en çok 3** varyant örneklenir (parametre tuzağı).
- Sayfalama (`?page=2`, `/page/2/`), takvim ve arama sonuç yolları şablon kümesine "düşük değer" olarak etiketlenir ve örneklemde ağırlığı azalır.

### 9.4 Örneklem seçimi (karar D7) `[B]`

Kaynağın "500 sayfa" sınırı yalnız prompt metnidir ve hiçbir kodla doğrulanmamıştır. Bizim kararımız:

| Parametre | Değer | Gerekçe |
|---|---|---|
| **Örneklem N, doğrulanmamış site** | **25 sayfa** | Kötüye kullanım ve yük sınırı (D11). Belge 01 §8.5: 30 sayfa altı güven **en çok orta** olur; bu kasıtlı bir sonuçtur |
| **Örneklem N, doğrulanmış site** | **50 varsayılan**, **200 üst sınır** | Doğrulanmış sahip için (Faz 3'te kod tarafı hazır; Faz 2a'da alfa kullanıcıları elle `verified` işaretlenir) |
| Sayfa kapasitesi kuralı | `N = f(sites.tier)` | `tier`, belge 04'te **site** üzerindedir (kullanıcı değil); bütçe `validate` aşamasında türetilir (belge 02 §8.2) |
| Sayfa modu | 1 sayfa | |

**Tabakalı örnekleme** `[B]`:
1. **Zorunlu:** ana sayfa, giriş URL'i, `robots.txt`'te veya `/` altında bulunan iletişim/hakkında/gizlilik sayfaları (varsa).
2. **Şablon kümeleme:** URL yolunu şablona indirge (`/blog/yazi-adi` → `/blog/*`, `/urun/123` → `/urun/*`); ilk iki yol segmenti + parametre kalıbı anahtardır.
3. Kalan kota şablonlara **boyutlarıyla orantılı** dağıtılır; her şablon en az 1, en çok `N/3` sayfa alır (tek şablon örnekleme baskın olmasın).
4. Şablon içinde seçim: sitemap `lastmod` en yeni + rastgele (sabit **tohum** ile; aynı denetim yeniden çalışırsa aynı örneklem, belge 01 P5 tekrarlanabilirlik).
5. Sitemap'te olmayıp ana sayfadan **bağlı** sayfalar da şablon kümelerine dahil edilir; "sitemap'te yok ama linkli" bir bulgudur (`linked-not-in-sitemap`).

**Kapsam ve güven için kayıtlı alanlar** `[B]`:

```json
"coverage": {
  "pages_discovered": 1840,
  "pages_planned": 50,
  "pages_fetched": 47,
  "pages_rendered": 6,
  "templates": [{"key": "/blog/*", "discovered": 1200, "sampled": 18}],
  "skipped": {"robots": 3, "error": 2, "out_of_scope": 14}
}
```

Belge 01'e etkisi: `pages_fetched < 30` → güven en çok **orta**; örneklem tek şablondan oluşuyorsa güven **düşük**.

### 9.5 Örneklem kullanıcıya nasıl anlatılır `[B]`
Rapor "Bu site 1.840 sayfa içeriyor; **25 sayfayı** örnekledik (doğrulanmış sitede 50) (şablon dağılımı: ...)" der. Sayı bir kesinlik iddiası değil, **kapsam bilgisidir**; bulgular örneklemde ölçülen oranlarla ("incelenen 47 sayfanın 12'sinde") ifade edilir. Tüm site için tahmin yapılmaz.

## 10. Nezaket (politeness) ve hata yönetimi `[B]`

Kaynakta bunların kodu yoktur `[doğrulandı]`; SKILL.md yalnız "5 eşzamanlı, 1 sn gecikme" ve "429'da yavaşla" der.

| Konu | Kararımız |
|---|---|
| Hedef host başına eşzamanlılık | **2** (SKILL.md'deki 5 yerine; paylaşımlı barındırmada daha güvenli) |
| İstekler arası gecikme | En az **500 ms** + titreşim (jitter); `Crawl-delay` varsa o (üst sınır 10 sn) |
| Küresel eşzamanlılık | Sistem genelinde hedef-başına ve toplam havuz; bir hedef diğer kullanıcıları yavaşlatmaz |
| 429 / 503 | `Retry-After` okunur; üstel geri çekilme (1, 2, 4 sn, ± jitter), **en çok 3 deneme**; hedef başına devre kesici: ardışık 5 hata → o denetimde taramayı durdur |
| Geçici hatalar (timeout, bağlantı sıfırlama) | 1 yeniden deneme |
| 4xx (404, 410) | Yeniden denenmez; bulgudur |
| 5xx | Bir kez yeniden denenir |
| Kısmi sonuç | Süre/bütçe dolarsa elde edilenle devam; `coverage` düşer, rapor "kısmi" der `[K: kısmi bulgu kalıbı]` |
| İptal | Kullanıcı iptal ederse in-flight istekler bırakılır, kısmi rapor üretilir |

**Denetim bütçesi** `[B]`: denetim başına en çok N sayfa, toplam indirme ≤ 200 MiB (tahmin `[?]`), toplam duvar saati ≤ 5 dk; kullanıcı/IP başına günlük denetim kotası (kötüye kullanım ve SSRF taraması önlemi).

## 11. Sahiplik ve kötüye kullanım `[?] D11`

Aracın hedefi herhangi bir site olabilir; bu bir **tarama aracı** ve bir "başkasının sitesine yük bindirme" vektörüdür. Öneri:

| Kullanıcı durumu | İzin |
|---|---|
| Doğrulanmamış | Sayfa modu + site modu **en çok 25 sayfa**, düşük hız, günlük kota |
| Doğrulanmış sahip (DNS TXT veya `<meta>`/dosya) | Site modu 50-200 sayfa, daha yüksek hız, zamanlanmış izleme (drift) |

Doğrulama mekanizması belge 04/06'da tasarlanır. Bu belgede yalnız fetch katmanının **kota ve hız parametrelerini dışarıdan alması** gerektiği not edilir.

## 12. Hata → `not_checked` eşlemesi

Belge 01'in "ölçülmedi" kavramını besleyen gerekçe kodları:

| Durum | Kod | Etkilenen |
|---|---|---|
| Giriş geçersiz/SSRF reddi | `target-rejected` | Skor üretilmez |
| DNS çözülemedi / bağlantı reddi | `unreachable` | Skor üretilmez |
| TLS el sıkışma hatası | `tls-handshake-failed` | Kapı 40 (belge 01 §8.3) |
| 4xx/5xx ana URL | `status-error` | Kapı 40 |
| robots.txt ulaşılamaz (5xx) | `robots-unreachable` | `requires:["robots"]` kontrolleri; AI crawler erişimi |
| robots giriş URL'ini engelliyor | `robots-disallows-entry` | Bulgu; kapı 70 değerlendirilir |
| Sitemap yok/bozuk | `sitemap-missing` / `sitemap-invalid` | `requires:["sitemap"]` kontrolleri |
| Header erişilemedi | `headers-unavailable` | `noindex-header` vb. |
| Render başarısız / zaman aşımı | `render-failed` | `js_gap`, render tabanlı kontroller |
| PSI/CrUX yok | `psi-unavailable` | Performans kategorisi |
| Dil desteklenmiyor | `language-unsupported` | Dile bağlı 2 kontrol (belge 01 §4.0) |
| Örneklem kısmi | `partial-sample` | Kapsam ve güven |
| Boşluksuz dil (zh/ja/th) | `words-not-measurable` | Kelime tabanlı kontroller `[K: words_measurable]` |

## 13. Test stratejisi `[K deseni]`

- **Düşmanca girdiler:** ondalık/hex/sekizlik IP, `user@host`, sondaki nokta, IPv4-mapped IPv6, zone id, private + public karışık A/AAAA, redirect → private, DNS rebinding simülasyonu, çok büyük gövde, gzip bombası, yavaş damlatma, devasa redirect zinciri. Kaynakta SSRF vakaları için `test_url_safety*.py` testleri var (72 + 45 + 14 test, `getaddrinfo` yamasına bağlı; yeniden yazılacak). Gövde boyutu, gzip bombası ve yavaş damlatma vakalarının kaynakta karşılığı **doğrulanmadı**, bunlar bizim yeni testlerimizdir.
- **Sahte sunucu fixture'ları:** SPA kabuğu, SSR sayfa, Wix tarzı yarı-boş sayfa, robots varyantları (grup seçimi, joker, `Allow` eşitliği), sitemap index + gzip + RSS.
- **Örneklem determinizmi:** aynı tohum + aynı giriş → aynı örneklem.
- **Nezaket:** sahte zamanlayıcıyla eşzamanlılık ve gecikme sınırı, 429 geri çekilme.
- **Egress kontrolü** (ağ seviyesi): staging'de worker'dan özel aralığa bağlantı denemesi **başarısız olmalı** (CI dışı, dağıtım doğrulaması).

## 14. Doğrulama matrisi (kaynak ↔ bu belge)

| İddia | Kontrol | Sonuç |
|---|---|---|
| Crawl kuyruğu kodda yok | `scripts/` altında crawl/frontier script'i aranıp bulunamadı; `ls | grep crawl` boş | ✅ |
| `can_fetch`/`robotparser` kullanılmıyor | `scripts/` genelinde arandı; yalnız `agentic_check` robots'u ayrıştırır | ✅ |
| 429/Retry-After/retry kodu yok | `fetch_page`, `url_safety`, `sitemap_discovery` içinde aranıp bulunamadı | ✅ |
| `max_redirects=5` (SKILL.md "3") | `fetch_page.py:113` | ✅ çelişki var |
| `MAX_PAGE_BYTES` 10 MiB, redirect gövdesi 64 KiB | `url_safety.py:1035,1039` | ✅ |
| Sitemap 50 MiB / 50 000 URL / 16 bildirilen / 50 çocuk / örnek 20 | `sitemap_discovery.py:69-77` | ✅ |
| Robots boyut sınırı 1 MiB | `MAX_ROBOTS_BYTES` | ✅ |
| Sitemap yaygın yolları (4 adet) | `COMMON_PATHS` | ✅ |
| `_is_spa` eşikleri 400 ve 100 karakter | `render_page.py:190,328-353` | ✅ |
| `js_gap` eşikleri %30 / 25 kelime / 3 link | `render_page.py:203-206` | ✅ |
| Render varsayılan 15 sn, viewport'lar | `render_page.py:149-154, 669` | ✅ |
| Varsayılan UA Chrome taklidi + `KaynakProje/2.0`; `--googlebot` seçeneği | `url_safety.py:899`, `fetch_page.py:72,377` | ✅ |
| `Accept-Language` bilinçli yok | `url_safety.py` yorumu | ✅ |
| Engellenen hostname'ler ve `100.64.0.0/10` | `url_safety.py:156-176, 214` | ✅ |
| Tüm A/AAAA kayıtları public olmalı; DNS64 istisnası | `validate_url_strict` gövdesi | ✅ |
| Chromium TOCTOU kalan riski | `SECURITY.md:58` | ✅ |
| Local-targets izin listesi yalnız üst düzey URL için | `url_safety.py` blok yorumu (`LOCAL_TARGETS`) | ✅ |

**Doğrulanmadı / bu turda okunmadı:** `url_safety._UNSAFE_IPV6_NETWORKS` içeriğinin tam listesi; `sitemap_discovery` `_Expansion` iç sınıfı; render'ın `block_resources` varsayılanları; render sırasında istek sayısı/bellek sınırı (kaynakta bulunamadı, bizim değerlerimiz tahmindir).

## 15. Açık kararlar

| # | Karar | Öneri | Not |
|---|---|---|---|
| **D7 ✅** | Örneklem büyüklüğü | **Katmana bağlı: doğrulanmamış 25, doğrulanmış 50 (üst sınır 200)**, tabakalı ve tohumlu | §9.4 (D11 ile uzlaştırıldı) |
| **D8** | Robots'a uyum: giriş URL'i istisnası | Giriş URL'i bir kez çekilir, diğerleri robots'a tabi | Hukuki/ürün onayı |
| **D9 ✅** | Teknoloji yığını | **Karar: Python ≥ 3.11.** Asenkron: `aiohttp` + özel `SafeResolver`, `playwright` (async), `lxml`/`beautifulsoup4`, `trafilatura` | §5.2. Kaynak script'ler (page_checks, parse_html, sitemap_discovery, transport_check, drift) büyük oranda doğrudan taşınır |
| **D10** | Bot kimliği ve bot bilgi sayfası | `SEOAnalyzerBot/1.0` + `/bot` sayfası + sabit IP aralığı | Alan adı belirlenmeli |
| **D11** | Sahiplik doğrulama ve kota katmanları | Doğrulanmamış 25 sayfa, doğrulanmış 50-200 | Belge 04/06 |
| **D12** | Render altyapısı: yönetilen mi kendi mi | Başlangıçta kendi izole worker + egress firewall | Güvenlik ve maliyet |
| D2, D4 | (belge 01'den) | %60 ve ilk sürümde kapalı | Değişmedi |

## 16. Sonraki belgeler

| Belge | Konu | Bu belgeden devraldığı |
|---|---|---|
| [`02-agent-arhitecture.md`](02-agent-arhitecture.md) | İş hattı, fan-out, checkpoint, LLM çağrıları | Bütçe, eşzamanlılık, kısmi sonuç, §10 nezaket |
| [`04-data-model.md`](04-data-model.md) | Audit/page/finding/score/coverage tabloları | §6.5 fetch sonucu ve §9.4 `coverage` sözleşmeleri |
| [`06-io-schemas.md`](06-io-schemas.md) | API ve rapor JSON şeması | `coverage`, `not_checked` gerekçe kodları (§12) |
| [`08-file-structure.md`](08-file-structure.md) | Dosya yapısı, portlama haritası | `safefetch`, `crawl`, `render` modül sınırları |
| [`09-implementation-roadmap.md`](09-implementation-roadmap.md) | Faz faz uygulama | Faz 0 prototipleri (P1, P3, P4), egress firewall önkoşulu |

> **Not:** Bu belge başlangıçta yalnız "Veri toplama" kapsamındaydı (`§1-§16`). Kullanıcının dosya planındaki adıyla **sistem tasarımı** belgesi olduğundan, genel sistem bileşenleri ve güven sınırları **Bölüm II** olarak aşağıda eklenmiştir.

---

# Bölüm II: Genel Sistem Tasarımı

> Bölüm I (§1-§16) veri toplama alt sistemini ayrıntılı tanımlar. Bu bölüm sistemin **bütününü** özetler: bağlam, bileşenler, güven bölgeleri, tehdit modeli, dağıtım ve dayanıklılık. Ayrıntılar ilgili belgelere bağlanır; burada tekrar edilmez.
> kaynak proje bir Claude Code eklentisidir ve **sunucu mimarisi içermez** `[doğrulandı: yapı: skills/agents/hooks/scripts]`; bu bölümün tamamı `[B]` bizim tasarımımızdır.

## 17. Sistem bağlamı

```
                        ┌────────────────────────────┐
   Kullanıcı ──────────▶│  SEO Analiz Servisi        │──────▶ Hedef siteler (internet)
 (tarayıcı / API)       │  (bu proje)                │        yalnız fetch ve render
                        └─┬────────┬────────┬────────┘
                          │        │        │
                          ▼        ▼        ▼
                   LLM sağlayıcı  PSI/CrUX  Google Search Console (Faz 3)
                   (Katman C)     (Faz 2a)  (OAuth, doğrulanmış site)

        Nesne depolama (HTML gövdeler, raporlar, PDF) · E-posta/webhook (Faz 3)
```

| Dış sistem | Ne için | Güven | Veri yönü | Faz |
|---|---|---|---|---|
| **Hedef siteler** | Fetch, render, robots, sitemap | **Düşmanca olabilir** | giriş (içerik), çıkış (istek) | 1 |
| LLM sağlayıcı | Katman C, Q&A | Güvenilir ama veri işleyen | çıkış: çıkarılmış alanlar (ham HTML değil) | 2b |
| PSI / CrUX | Performans | Güvenilir | çıkış: URL | 2a |
| Google Search Console | Google görünümü | Güvenilir, kiracı OAuth | iki yönlü | 3 |
| Nesne depolama | Gövde, rapor, PDF | Güvenilir | iki yönlü | 1 |
| E-posta / webhook | Bildirim | Güvenilir | çıkış | 3 |

## 18. Bileşenler ve sorumluluklar

Çalışma zamanı bileşenleri belge 02 §3'tedir (API, Control, Fetch, Render, Analyze, LLM, Report, PostgreSQL, Redis, nesne depolama, egress proxy). Özet:

| Bileşen | Sorumluluk | Durum tutar mı | Güven bölgesi |
|---|---|---|---|
| **API** (FastAPI) | Kimlik, kota, doğrulama, SSE, rapor sunumu | Hayır (stateless) | Z1 |
| **Control** | Durum makinesi, fan-in, bütçe, sonuç alıcı (§3.2, belge 02) | DB | Z2 |
| **Fetch** | SSRF doğrulama, HTTP, robots, sitemap, transport | Hayır | **Z3** |
| **Render** | Playwright, `js_gap` | Hayır (tek kullanımlık bağlam) | **Z3** |
| **Analyze** | Kontroller, skor | Hayır | Z2 |
| **LLM** | Katman C, Q&A, BYOK çözme | Hayır | Z2 (yalnız LLM sağlayıcısına çıkış) |
| **Report** | `audit.json` doğrulama, HTML/PDF | Hayır | Z2 |
| PostgreSQL | Kalıcı durum | Evet | Z2 |
| Redis | Kuyruk, oran sınırı, semafor, akış, pub/sub | Geçici | Z2 |
| Nesne depolama | Gövdeler, raporlar | Evet | Z2 |
| **Egress proxy** | Z3 çıkışını denetler, özel aralığı **ağ seviyesinde** reddeder | Hayır | Z3 sınırı |

## 19. Güven bölgeleri ve ağ kuralları

| Bölge | Kimler | Neye erişebilir | Neye **erişemez** |
|---|---|---|---|
| **Z0 İnternet** | Kullanıcılar, hedef siteler | – | – |
| **Z1 Kenar** | API, statik rapor sunumu | Z2'deki Redis/DB (dar rol), kullanıcı kimliği | Fetch/Render, LLM anahtarları |
| **Z2 İç** | Control, Analyze, LLM, Report, DB, Redis, depolama | birbirleri (kurallı), LLM sağlayıcı (yalnız LLM worker) | **Hedef siteler** (Z2'den doğrudan dış istek yok) |
| **Z3 Çıkış-izole** | Fetch, Render | Egress proxy üzerinden **yalnız genel internet**; nesne depolamaya ön imzalı yazma; Redis akışına yazma | DB, sırlar, iç servisler, özel IP aralıkları, bulut metadata, diğer kiracı verisi |

**Kural özeti:**
1. **Hedef sitelere yalnız Z3 konuşur.** Z2'deki hiçbir bileşen (LLM hariç, yalnız sağlayıcıya) dış istek yapmaz.
2. Z3 → DB yok (belge 02 §3.2). Z3 → Z2 yalnız ön imzalı URL ve Redis akışı.
3. Egress proxy, uygulama içi SSRF kontrolünden **bağımsız** son savunmadır (belge 05 §5.3): RFC1918, link-local, `100.64.0.0/10`, metadata adresleri **ağ düzeyinde** reddedilir.
4. LLM worker yalnız LLM sağlayıcısının adresine çıkabilir (allow-list), hedef sitelere çıkamaz.
5. Z1 (API) hiçbir hedef URL'e bağlanmaz; yalnız iş kuyruğa koyar.

**Sır haritası:**

| Sır | Nerede çözülür | Kim görür |
|---|---|---|
| DB parolaları (rol başına) | Z2 worker'ları, API | Sadece ilgili rol |
| Kullanıcı BYOK anahtarı | **Yalnız LLM worker** belleğinde | Başka hiçbir bileşen |
| GSC OAuth token | GSC bağlayıcı (Faz 3), ayrı dar rol | – |
| Nesne depolama anahtarı | Control, Report (Z3'e ön imzalı URL verilir) | Z3 anahtarı görmez |
| LLM sağlayıcı anahtarı (platform) | LLM worker | – |

## 20. Tehdit modeli (özet)

| # | Tehdit | Saldırgan | Etki | Başlıca önlem | Ayrıntı |
|---|---|---|---|---|---|
| T1 | **SSRF** (iç ağa/metadata'ya istek) | Kötü niyetli kullanıcı veya hedef | Sır sızması, iç ağ erişimi | Politika + `SafeResolver` + **egress proxy** | belge 05 §5 |
| T2 | **DNS rebinding** | Kötü niyetli hedef | Aynı | Resolver'da çözümleme anında doğrulama; ağ seviyesinde engel | belge 05 §5.2 |
| T3 | **Chromium kaçışı / render TOCTOU** | Kötü niyetli hedef | Z3 ele geçirilir | Z3 sırsız, DB'siz, tek kullanımlık bağlam, egress firewall | belge 05 §5.3, belge 02 §3.2 |
| T4 | **Prompt injection** | Hedef sayfa | Yanlış rapor, veri sızdırma | Zarflama, araçsız model, şema, kanıt doğrulama | belge 03 §4.3, §9, §10 |
| T5 | **Kiracılar arası veri sızması** | Kullanıcı | Gizlilik ihlali | `tenant_id` + RLS, bileşik FK, test | belge 04 |
| T6 | **BYOK anahtarı sızması** | İçeriden/dışarıdan | Maliyet, hesap ele geçirme | Zarf şifreleme, yalnız LLM worker, loglama yasağı, sızıntı taraması | belge 04, 09 Faz 2b |
| T7 | **Hedef siteye yük bindirme** (kötüye kullanım) | Kullanıcı | İtibar, hukuki | Hedef-başına sınır (kiracılar arası), kota, devre kesici, dış istek kaydı | belge 05 §10, belge 02 §15 |
| T8 | **Maliyet kötüye kullanımı** (LLM) | Kullanıcı | Maliyet | Bütçe nesnesi, kota, önbellek, K≤5 | belge 02 §8-9 |
| T9 | **Rapor üzerinde XSS** (`evidence` sayfadan gelir) | Hedef sayfa | Kullanıcı oturumu | Çıktıda zorunlu kaçışlama, CSP, evidence düz metin | belge 06 |
| T10 | **Paylaşım bağlantısı tahmini** | Saldırgan | Rapor sızması | İmzalı, süreli, yüksek entropili; `noindex` | belge 06 |
| T11 | **Tedarik zinciri** (bağımlılıklar) | Üçüncü taraf | Kod yürütme | Sürüm sabitleme, hash doğrulama, bağımlılık taraması (kaynak da CVE notlu alt sınırlar kullanır `[doğrulandı: requirements.txt]`) | belge 08 §12 |
| T12 | **Veri saklama/gizlilik ihlali** | – | Hukuki | Saklama süresi, silme sırası, KVKK/GDPR envanteri | belge 04 §6 |
| T13 | **Hedef sayfadan zararlı içerik indirme** (gzip bombası, devasa gövde) | Hedef | Kaynak tüketimi | Bayt/süre/derinlik sınırları | belge 05 §6.1 |

## 21. Dağıtım topolojisi `[?]`

```
 [CDN/WAF] ─▶ [API x N]  ──▶ [PostgreSQL (birincil + okuma kopyası sonra)]
                 │             [Redis (kuyruk/akış)]    [Nesne depolama]
                 ▼
         [Control x N] [Analyze x N] [LLM x N] [Report x N]        (Z2, özel alt ağ)
                 ▲
        Redis akışı + ön imzalı URL
                 │
         [Fetch x N]   [Render x N]  ──▶ [Egress proxy] ──▶ internet   (Z3, ayrı hesap/ağ)
```

| Konu | Karar (öneri) | Not |
|---|---|---|
| Paketleme | Worker türü başına ayrı konteyner imajı (belge 08) | Z3 imajları **minimal** (sır yok) |
| Ortamlar | dev (docker-compose) · staging · prod | Staging'de egress firewall **dağıtım testi** zorunlu |
| Ölçekleme | Kuyruk derinliğine göre worker sayısı | `q_fetch`, `q_render`, `q_llm` |
| Hesap ayrımı | Z3 ayrı bulut hesabı/proje/VPC | Ele geçirme etkisini sınırlar |
| Gizli yönetimi | Yönetilen sır deposu (SD3) | Ortam değişkenlerinde düz parola yok |
| Kod olarak altyapı | **Faz 0'da seçilir** (SD4) | |
| Barındırma | **Açık** (SD1) | Z3 izolasyonu ve egress denetimi gereksinimi seçimi kısıtlar |
| Sıfır kesinti | `SIGTERM`'de yeni iş almama, lease ile devralma (belge 02 §16) | |

## 22. Dayanıklılık: bileşen çökmesinde davranış

| Bileşen düşerse | Etki | Davranış |
|---|---|---|
| **Redis** | Kuyruk, semafor, SSE durur | Çalışan işler lease sonunda yeniden alınır; yeni denetim `queued` kalır, API 503 + yeniden dene; **veri kaybı yok** (durum DB'de) |
| **PostgreSQL** | Hiçbir aşama ilerleyemez | Worker'lar bekler/yeniden dener; API salt-okunur hata; yazılamayan akış kaydı Redis'te bekler |
| **Nesne depolama** | Gövde yazılamaz | Fetch aşaması `partial`; `body_ref` olmadan analiz yapılamaz → ilgili sayfa `error` |
| **Egress proxy** | Fetch/Render tamamen durur | Denetimler `queued`/`failed`; **doğrudan çıkışa geçilmez** (fail-closed) |
| **LLM sağlayıcı** | Katman C yapılamaz | Katman A/B raporu **yine üretilir**; danışma/Q&A "üretilemedi"; bütçe harcanmaz |
| **PSI/CrUX** | Performans ölçülemez | `psi-unavailable`; kapsam düşer, rapor üretilir |
| **Render filosu** | `js_gap` yok | Ham HTML ile devam, `render-failed` |
| **Tek worker** | O iş yarıda kalır | Lease sonrası başka worker devralır (idempotent) |

**Fail-closed ilkesi:** güvenlikle ilgili bileşen (egress proxy, SSRF politikası) çalışmıyorsa sistem **açılmaz**, "doğrudan bağlan" yoluna düşmez.

## 23. Kapasite modeli (parametreler, değerler ölçülecek)

Gerçek sayı uydurmuyoruz; model şu girdilerle Faz 1-2a'da doldurulur:

| Parametre | Sembol | Nereden ölçülür |
|---|---|---|
| Denetim başına örneklem | `N` (25/50/200, D7) | Belge 05 §9.4 |
| Ortalama gövde boyutu | `B` | Faz 1 gerçek siteler |
| Render edilen sayfa | `K` (≤5) | Belge 05 §7.3 |
| Render başına bellek ve süre | `Mr`, `Tr` | P3 prototipi |
| Hedef-başına eşzamanlılık | `c` (=2) | Belge 05 §10 |
| Katman C çağrısı/denetim | `Lc` | Belge 03, Faz 2b |
| Ortalama LLM maliyeti/denetim | `Cl` | Faz 2b ölçümü |

Türetilen: fetch süresi ≈ `N × t_fetch / c`; depolama ≈ `N × B × saklama_günü × günlük_denetim`; render eşzamanlılığı = worker × 2. **Boyutlandırma Faz 1 sonunda bu ölçümlerden yapılır.**

## 24. Gözlemlenebilirlik ve işletme

Günlük, metrik, alarm ve dış istek kaydı belge 02 §15'tedir. Sistem düzeyinde eklenenler:
- **Sağlık uç noktaları:** her bileşen için canlılık ve hazırlık; egress proxy ve nesne depolama bağımlılık kontrolleri.
- **Operatör paneli (FT5):** kiracı, denetim, devre kesici durumu, engel listesi, istek günlüğü araması; genel yayın önkoşulu.
- **Kötüye kullanım çalışma kitabı:** şikayet alınınca hangi kiracı/ne zaman sorgusu, engelleme adımı, geri bildirim (D16).
- **Yedekleme:** PostgreSQL zaman noktası kurtarma; nesne depolama sürüm/yaşam döngüsü kuralı; geri yükleme tatbikatı (Faz 3).

## 25. Genel sistem doğrulama matrisi

| İddia | Kontrol | Sonuç |
|---|---|---|
| kaynak proje sunucu mimarisi içermez (eklenti) | Dizin yapısı: `skills/`, `agents/`, `hooks/`, `scripts/`, `extensions/` | ✅ |
| Kaynak bağımlılıkları CVE notlu alt sınırlarla sabitler | `requirements.txt` yorumları (örn. urllib3, lxml, requests) | ✅ |
| Chromium DNS'i kendi çözer, Python pin'i ulaşmaz | `SECURITY.md:58`, `url_safety.py` yorumları | ✅ (Bölüm I §5.3) |
| Diğer maddeler (bölgeler, dağıtım, kapasite) | Bizim tasarımımız; kaynakta karşılığı yok | `[B]` |

**Doğrulanmadı:** egress proxy ürününün (Squid/özel) Z3 gereksinimlerini (özel aralık reddi, TLS geçişi, günlük) karşıladığı; seçilen barındırmada Z3 hesap/ağ ayrımının maliyeti; Redis Streams'in çökme senaryolarında teslim semantiği. Faz 0 prototiplerinde (P2, P3) ele alınır.

## 26. Açık kararlar (sistem tasarımı, önek `SD`)

| ID | Karar | Öneri | En geç |
|---|---|---|---|
| SD1 | Barındırma platformu (bulut/sağlayıcı) | Z3 ayrı hesap/ağ ve egress denetimini destekleyen bir platform; seçim Faz 0 | Faz 0 sonu |
| SD2 | Egress proxy ürünü | Özel aralık ve metadata reddi ağ seviyesinde, istek günlüğü; P3'te karşılaştırılır | Faz 0 sonu |
| SD3 | Sır yönetimi | Yönetilen sır deposu + zarf şifreleme anahtarı | Faz 1 |
| SD4 | Kod olarak altyapı aracı | Faz 0'da seçilir | Faz 0 |
| SD5 | Veritabanı yüksek erişilebilirlik ve yedekleme düzeyi | Yönetilen PostgreSQL, zaman noktası kurtarma | Genel yayın |
