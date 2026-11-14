# 00. Yetenek Karşılaştırması: kaynak projede Olup Bizde Kaybolabilecekler

> Durum: **Canlı belge v0.2** (telafi kararları işlendi, bkz. §3.1) · Her mimari belge bu listeyi günceller.
> Soru: "kaynak projenin yapabildiği bir şeyi bizim ürün artık yapamaz hale gelebilir mi?"
> Kısa cevap: **Evet, ama yalnızca aşağıdaki "Bilinçli kayıplar" bölümünde yazılı olanlar.** Yığın Python olduğu için dil değişikliğinden kaynaklanan kayıp yoktur. Diğer her şey korunur, dönüştürülür veya tarihli bir yol haritasına yazılır.

İşaretler: `[K]` kaynak · `[B]` bizim kararımız · `[doğrulandı]` kaynak kodla kontrol edildi

---

## 1. Yığın kararının etkisi

kaynak proje Python'dur (`requires-python >= 3.11`, `pyproject.toml` `[doğrulandı]`). Bu yüzden:

| Konu | Etki |
|---|---|
| `page_checks`, `parse_html`, `sitemap_discovery`, `transport_check`, `drift_*`, `schema_generate`, `content_quality` | **Mantık kaybı yok**, kod doğrudan taşınabilir (MIT; telif ve atıf korunur) |
| Kaynağın test paketi | Doğrudan yeniden kullanılır (§4) |
| `url_safety._pin_dns` (global `getaddrinfo` yaması) | **Taşınmaz.** Eşzamanlı sunucuda çalışmaz `[doğrulandı: 05]`. Yerine `aiohttp` özel resolver (belge 05 §5.2). Politika aynen korunur, uygulama değişir |
| CLI / alt süreç + stdout JSON çalışma modeli | Fonksiyon çağrısına çevrilir (aynı kod, farklı giriş noktası) |

Yani Python seçimi, TypeScript'e göre **kayıp riskini azaltır**: yeniden yazım hatası riski yoktur, yalnız yeniden paketleme vardır.

## 2. Yetenek matrisi

Durumlar: **Korunur** (aynı kalite) · **Dönüştürülür** (farklı biçim, aynı sonuç) · **Ertelenir** (yol haritasında, tarihli) · **Kaybedilir** (bilinçli, gerekçeli)

### 2.1 Çekirdek ölçüm

| Yetenek (kaynak) | Durum | Not |
|---|---|---|
| 47 deterministik sayfa kontrolü (`page_checks.py`) | **Korunur** | Aynı id, severity, eşik; Türkçe'de 2 kontrol kapalı (belge 01 §4.0) |
| TLS / header / HTTP→HTTPS (`transport_check.py`) | **Korunur** | |
| Sitemap keşfi ve doğrulama, 50 MiB / 50 000 URL sınırları | **Korunur** | |
| SPA tespiti ve `js_gap` | **Korunur** | |
| SSRF politikası (IP aralıkları, DNS rebinding reddi, redirect doğrulaması) | **Korunur** (politika) / **Dönüştürülür** (uygulama) | Belge 05 §5 |
| Kodlama çözme sırası (BOM → header → meta → utf-8) | **Korunur** | Türkçe karakterler için kritik |
| Okuma sınırları (10 MiB, 64 KiB redirect gövdesi, JSON derinliği) | **Korunur** | |
| Güvenilmeyen içerik / prompt injection kuralı | **Korunur** | |
| CWV eşikleri, PSI/CrUX | **Korunur** | |
| Drift: 17 kural, SQLite anlık görüntü | **Dönüştürülür** | Veritabanına taşınır (Faz 3) |
| Google güncelleme defteri (`data/google-updates.json`, `seo_updates.py`) | **Korunur** | Kaynaklı ve tarihli kural verisi |
| İçerik kalite kapıları (sayfa tipine göre kelime eşiği) | **Korunur** | |

### 2.2 Değerlendirme ve rapor

| Yetenek | Durum | Not |
|---|---|---|
| Health Score (7 kategori) | **Dönüştürülür** | LLM yerine kod hesaplar. Skorlar kaynak proje skorlarıyla **kıyaslanamaz** (yöntem farklı) |
| Page Score Card (5 kategori) | **Korunur** | |
| Severity tanımları ve aksiyon planı fazları | **Korunur** | |
| E-E-A-T analizi | **Dönüştürülür** | Skora girmez, "danışma skoru" olur (D3) |
| `audit-data.json` zarfı | **Dönüştürülür** | JSON Schema'lı, genişletilmiş |
| PDF rapor (WeasyPrint) | **Ertelenir** | Önce HTML; PDF Faz 3 |
| Rapor kalite kapısı (`_review_pdf`) | **Dönüştürülür** | Şema + HTML doğrulayıcı |

### 2.3 Uzman modüller

| Yetenek (kaynak skill/ajan) | Durum | Hedef |
|---|---|---|
| `seo-schema` doğrulama | **Korunur** | Faz 1 |
| `seo-schema` **üretim** (`schema_generate.py`: hazır JSON-LD) | **Ertelenir**, öncelikli | Faz 2. Kullanıcıya "kopyala-yapıştır düzeltme" değeri yüksek |
| `seo-technical`, `seo-sitemap`, `seo-images`, `seo-page` | **Korunur** | Faz 1 |
| `seo-performance` | **Korunur** | Faz 2 (PSI anahtarı) |
| `seo-content` (E-E-A-T) | **Dönüştürülür** | Faz 2, danışma skoru |
| `seo-geo` / `seo-agentic` (AI arama hazırlığı) | **Dönüştürülür** | Faz 2. Robots AI bot erişimi, llms.txt, `js_gap` deterministik; yorum LLM |
| `seo-visual` (ekran görüntüsü, mobil) | **Ertelenir** | Faz 3, depolama maliyeti |
| `seo-drift` | **Ertelenir** | Faz 3 |
| `seo-google` (GSC, GA4, CrUX geçmişi, Indexing API) | **Ertelenir** | Faz 3, çok kiracılı OAuth gerekir |
| `seo-hreflang` (tam denetim) | **Ertelenir** | Yalnız `hreflang-missing-self` kontrolü Faz 1'de |
| `seo-backlinks` (Moz/Bing/Common Crawl) | **Ertelenir** | Faz 4 |
| `seo-local`, `seo-maps`, `seo-ecommerce` | **Ertelenir** | Faz 4+ |
| `seo-sxo`, `seo-cluster`, `seo-content-brief`, `seo-competitor-pages`, `seo-programmatic`, `seo-plan`, `seo-flow` | **Ertelenir** | Faz 4+ (üretim/strateji odaklı, SERP verisi gerekir) |
| `seo-image-gen` | **Ertelenir** | Düşük öncelik |
| Extension'lar (DataForSEO, Ahrefs, Firecrawl, SE Ranking, Profound, Bing, Matomo, Unlighthouse) | **Ertelenir** | İhtiyaç doğarsa, birer birer |

## 3. Bilinçli kayıplar

Bunlar yalnız yapılmayacak değil, **ürün kararı olarak yapılamaz** olacak şeylerdir.

| # | Kaybedilen yetenek | Neden | Hafifletme |
|---|---|---|---|
| L1 | **Yerel / staging / özel ağ denetimi** (`LOCAL_TARGETS`). kaynak proje ile yayına almadan önce site denetlenebiliyordu | Çok kiracılı SaaS'ta bu bir SSRF deliğidir; kaynak da yalnız üst düzey URL için izin veriyor `[doğrulandı]` | **Karar: ilk etapta kapsam dışı**, yalnız internetteki canlı siteler denetlenir (§3.1). SaaS'ta bu özellik hiçbir zaman açılmaz |
| L2 | **Googlebot kimliğiyle fetch** (`--googlebot`, prerender tespiti) | Üçüncü tarafın kimliğini taklit etmek; Google IP doğrulayan WAF'larda zaten yanlış sonuç verir | `js_gap` (ham vs render) dinamik render'ı kısmen yakalar; sınır raporda yazılır |
| L3 | **Serbest biçimli LLM etkileşimi**: kullanıcı Claude Code'da istediği komutu/alt komutu istediği sırayla çalıştırabiliyordu | Ürün sabit, test edilebilir bir akıştır | Akış parametreleri (mod, kapsam) kullanıcıya açık; ad-hoc sorgular sonraki "soru sor" özelliği olabilir |
| L4 | **Skorda LLM yargısının rolü**: Health Score'a öznel nüans giriyordu | Tekrarlanabilirlik önceliklidir (belge 01 P1) | Danışma skoru ayrı gösterilir; kanıtlı yorum bulgularda kalır. **Karar: ek telafi yapılmaz** (§3.1) |
| L5 | **Hacim iddiası "500 sayfa"** | Kodla doğrulanmamış prompt metniydi `[doğrulandı: crawler yok]`; biz 50 örneklem / 200 üst sınır veriyoruz | Kapsam raporda açıkça yazılır; doğrulanmış sahipler için artırılır |
| L6 | **Kullanıcının kendi Claude aboneliğiyle çalışma** (maliyet kullanıcıdaydı) | Ürün olarak LLM maliyeti bize ait | Katman C'yi sınırlı tutmak, önbellek, plan katmanları |
| L7 | **Katman B (heuristik içerik kalıpları) Türkçe'de** | Kalıp listeleri İngilizce `[K]`; D5 kararı | İngilizce sayfalarda açık kalır; Türkçe listeler yazılınca açılır |

L5 dürüst bir notla: bu bir *gerileme* değildir, çünkü kaynak projenin 500 sayfa taraması kod olarak hiç var olmamıştır. Ama kullanıcı gözünde "daha az sayfa taranıyor" olarak algılanabilir. Bunu ürün dilinde "örneklem + kapsam raporu" olarak anlatmak gerekir.

## 3.1 Telafi planı ve kararlar

| # | Karar | Durum | Faz |
|---|---|---|---|
| L1 | Yerel/staging denetimi **ilk etapta gerekmiyor**; yalnız internetteki canlı siteler. HTML yükleme modu ve self-hosted sürüm planlanmaz | **Kapsam dışı** (kullanıcı kararı) | – |
| L2 | Doğrulanmış sahipler için GSC URL Inspection; genel kullanıcıda `js_gap` + açık sınır notu | **Planlı** (zaten Faz 3'te) | 3 |
| L3 | Rapor üzerinde soru-cevap + modül yeniden çalıştırma düğmeleri (§3.2) | **Planlı** | 2-3 |
| L4 | Skorda LLM nüansı için **telafi yapılmaz**. Danışma skoru (D3) tek istisna olarak kalır | **Karar: yapılmaz** | – |
| L5 | Doğrulanmış sahiplere 200 sayfa, dönen örneklem, kullanıcı tanımlı URL'ler (§3.3) | **Planlı** | 2-3 |
| L6 | Önbellek, Katman C'yi sınırlı sayfada çalıştırma, küçük model varsayılanı, plan katmanları, BYOK (§3.4) | **Planlı** | 2-3 |
| L7 | Türkçe stopword, filler ve CTA listeleri (§3.5) | **Planlı** | 2 |

### 3.2 L3: Rapor üzerinde soru-cevap `[B]`

- **Kaynak:** LLM yalnız kaydedilmiş `audit.json` (bulgular, kanıtlar, skorlar) üzerinden cevap verir. **Yeniden fetch yapmaz**, sayfaya gitmez. Bu, hem maliyeti hem SSRF/prompt-injection yüzeyini sınırlar.
- **Atıf zorunlu:** her cevap ilgili `finding id` ve `url` değerlerine bağlanır. Raporda karşılığı olmayan iddia reddedilir ("bu raporda ölçülmedi").
- **Güvenilmeyen içerik kuralı:** bulgulardaki `evidence` alanı sayfadan geldiği için talimat sayılmaz (belge 01 P7).
- **Modül yeniden çalıştırma düğmeleri:** deterministik modüller (Katman A) ucuzdur ve serbesttir; Katman C modülleri kullanıcının LLM kotasından düşer. Yeniden çalıştırma yeni bir `audit run` üretir, eskisinin üzerine yazmaz.
- **Maliyet sınırı:** denetim başına soru sayısı ve token tavanı; sık sorulan sorular önbelleğe alınır.
- **Kapsam:** kullanıcı rapor dışı konularda (genel SEO sohbeti) cevap alamaz; bu bir sohbet botu değil, rapor yorumlayıcıdır.

### 3.3 L5: Hacim `[B]`

Üç bileşen, birbirinden bağımsız:

1. **Doğrulanmış sahip:** 200 sayfaya kadar örneklem (belge 05 D11).
2. **Dönen örneklem:** zamanlanmış denetimlerde farklı tohumla farklı sayfalar seçilir; **birikimli kapsam** ayrıca gösterilir.
3. **Kullanıcı tanımlı URL'ler:** kullanıcı "bu sayfaları her denetime ekle" diyebilir (tavanlı, aynı scope içinde).

**Tasarım uyarısı (skor karşılaştırılabilirliği):** örneklem değişirse skor da değişir; bu, "değişiklik yapmadım ama skor oynadı" şikayetini doğurur ve trend grafiğini bozar. Bu yüzden iki örneklem tutulur:

| Örneklem | İçerik | Skora etkisi |
|---|---|---|
| **Çekirdek (sabit)** | Ana sayfa, giriş URL'i, kullanıcı tanımlı URL'ler, şablon başına sabit temsilci | **Trend skorunu belirler**, denetimler arası karşılaştırılabilir |
| **Keşif (dönen)** | Kalan kotaya dönen tohumla seçilen sayfalar | Yalnız **bulgu keşfi** ve birikimli kapsam; trend skoruna girmez |

### 3.4 L6: LLM maliyeti `[B]`

| Önlem | Detay |
|---|---|
| Önbellek | Anahtar: `içerik_hash + rubrik_sürümü + model_id` (belge 01 §4.1). İçerik değişmediyse LLM tekrar çağrılmaz |
| Sınırlı Katman C | LLM yalnız **K ≤ 5** sayfada çalışır (ana sayfa + şablon temsilcileri; render bütçesiyle aynı küme, belge 05 §7.3) |
| Model katmanlaması | Varsayılan küçük/hızlı model; derin analiz üst plana bağlı, `[K: Sonnet varsayılan, yalnız yargı ağırlıklı ajanlarda Opus]` |
| Plan katmanları | Aylık LLM kotası ve denetim sayısı plana bağlı |
| **BYOK** | Kullanıcı kendi API anahtarını getirir. **Yalnız Katman C için**; Katman A her zaman bizim. Anahtar şifreli saklanır (kiracı başına, KMS veya eşdeğeri), **hiçbir log'a yazılmaz**, ekranda maskelenir, silme/rotasyon desteklenir. Kimlik/kiracı modeli belge 04'te |
| Maliyet görünürlüğü | Her denetimde tahmini ve gerçekleşen LLM maliyeti kayda yazılır; bütçe aşımında Katman C otomatik durur (`partial`) |

### 3.5 L7: Türkçe dil desteği `[B]`

Bu iş yapılana kadar belge 01 §4.0'daki durum geçerlidir (Katman B kapalı, 2 Katman A kontrolü kapalı).

| Parça | Yapılacak | Not |
|---|---|---|
| Türkçe stopword listesi | `title-not-reflected-in-content` ve `description-not-reflected-in-content` için | **Lisans kontrolü** gerekir (açık listelerin lisansları farklı) |
| Ek yapısı | Türkçe sondan eklemeli bir dildir (`ürün`, `ürünler`, `ürünlerimiz`); sözcük eşleşmesi köke veya önek eşleşmesine ihtiyaç duyabilir | **Doğrulanmadı**: gerekli olup olmadığı Türkçe örneklemle ölçülmeli. Gerekirse hafif kök çıkarıcı değerlendirilir |
| Filler/CTA kalıpları (Katman B) | Türkçe "yapay metin kalıpları", şablonlu CTA'lar ("Hemen deneyin", "Şimdi başlayın") | Kendi üretimimiz; kaynak listeleri CC BY-SA olduğundan birebir almıyoruz (§6) |
| Doğrulama | Türkçe kalibrasyon seti (20-30 site); yanlış pozitif oranı ölçülür | Açılış kriteri: kabul edilebilir yanlış pozitif eşiği (belirlenecek `[?]`) |
| Açılış | Kriter sağlanınca iki kontrol ve Katman B dil bazında açılır | Rapor `language-unsupported` notunu kaldırır |

**Not:** Katman B İngilizce sayfalarda zaten açık kalır; bu iş yalnız Türkçe'yi kapsar.

---

## 4. Gerileme olmaması için güvence (testle)

"Yapabildiği şeyi artık yapamaması" ancak testle engellenir. Kaynağın test paketi `tests/` altında 100+ dosyadır `[doğrulandı: dizin sayımı, 04/05 raporları]`. Taşınabilecek, doğrudan gerileme kalkanı olacak testler:

| Kaynak test | Neyi korur |
|---|---|
| `test_page_checks.py` | 47 kontrolün tetiklenmesi, near-miss, temiz örnek; severity eşlemesi |
| `test_transport_check.py` | TLS/header/redirect bulguları |
| `test_url_safety.py` (72 test), `_ipv6.py` (45), `_port_pin.py` (14) | SSRF **politikası**. **Dikkat:** bu testler `socket.getaddrinfo` yamasına bağlıdır (dosyalarda 62/41/10 geçiş) `[doğrulandı]`; yeni resolver'a **değişmeden çalışmaz**. Politika davranışı (hangi IP/hostname reddedilir) korunur, testler `SafeResolver` adaptörüyle **yeniden yazılır** ve `_port_pin` testleri (yerel hedef izin listesini sınar, biz o özelliği almıyoruz) **kapsam dışı** kalır |
| `test_hostile_inputs.py` | **SSRF testi değildir** (düzeltme): agentic/robots, JSON derinliği, Keywords Everywhere ve Lighthouse ayrıştırıcılarının bozuk girdi davranışını sınar `[doğrulandı]`. İlgili modüller taşındığında (Faz 2a+) oradaki testler taşınır |
| `test_drift_*.py` | Drift kuralları ve URL normalizasyonu |
| `test_content_quality.py` | Heuristik tespitleri (yalnız İngilizce fixture) |
| `test_backlink_score_gate.py` | "Ölçülmeyene skor verme" kapısı (genel kurala örnek) |

Kural `[B]`: **Bir kontrol, kural veya güvenlik davranışı taşındığında, kaynağın ilgili testi (veya eşdeğeri) önce yeşil olmalıdır.** Test taşınamıyorsa nedeni bu belgede yazılır. Böylece "sessiz kayıp" olmaz.

Ek: **karşılaştırma testi** (golden): aynı HTML + header → kaynak `page_checks` çıktısı ile bizim çıktı **bulgu id ve severity açısından aynı** olmalı. **Düzeltme:** kaynakta hazır bir fixture kütüphanesi **yoktur**: `tests/fixtures/` yalnızca 2 alakasız dosya içerir (DataForSEO araç listesi ve Lighthouse PSI örneği) ve `test_page_checks.py` HTML'ini satır içi taşır `[doğrulandı]`. Parity vakaları test dosyalarından **çıkarılarak** üretilir (belge 08 portlama haritası). Farklı olması gerekiyorsa (ör. Türkçe'de kapalı 2 kontrol) fark belgelenir.

## 5. Süreç kuralları

1. Hiçbir yetenek bu tabloya yazılmadan **kapsamdan çıkarılmaz**.
2. Yeni "Kaybedilir" satırı, gerekçe ve hafifletme olmadan eklenemez.
3. "Ertelenir" satırlarının bir faz hedefi vardır; faz hedefi olmayan satır "Kaybedilir"e dönüştürülür veya silinir.
4. Her mimari belgenin sonunda bu tablo gözden geçirilir.

## 6. Lisans ve atıf `[K]`

Repo MIT. Kod taşınırken telif metni ve kaynak atfı korunur. Ek yükümlülükler: `content_quality.py` / `content_humanize.py` kalıp listeleri CC BY-SA 4.0 (Wikipedia "AI Cleanup") ve MIT  kaynaklıdır; `page_checks.py` web-obs'tan (MIT) türemiştir; FLOW promptları CC BY 4.0 `[doğrulandı: 05 raporu]`. Kalıp listelerini birebir almak yerine kendi (özellikle Türkçe) listelerimizi üretmek share-alike yükümlülüğünden kaçınır.
