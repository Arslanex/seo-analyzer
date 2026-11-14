# 10. Karar Günlüğü

> Durum: **Canlı belge v0.1** · Tüm mimari kararların tek kaydı. Her faz sonunda güncellenir (belge 09 §12).
> Belge numaraları **nihai** numaralandırmadır: 00 capability-parity · 01 evaluation-system · 02 agent-arhitecture · 03 rubrik-and-prompts · 04 data-model · 05 system-design · 06 io-schemas · 07 features · 08 file-structure · 09 implementation-roadmap · 10 decision-log.

---

## 1. Kimlik şeması ve durumlar

Belgeler paralel yazıldığı için aynı `D13`-`D20` numaraları farklı kararlar için kullanılmıştı. Bu günlükte **tüm kararlar benzersiz kimlik** alır ve ilgili belge **öneki** taşır.

| Önek | Anlam | Kaynak belge |
|---|---|---|
| `D` | Çekirdek mimari kararlar (D1-D16) | 01, 02/05, 02 (iş hattı) |
| `L` | Kayıp ve telafi kararları (L1-L7) | 00 |
| `R` | Rubrik ve prompt kararları | 03 |
| `DM` | Veri modeli kararları | 04 |
| `IO` | API ve rapor şeması kararları | 06 |
| `FT` | Ürün özelliği ve plan kararları | 07 |
| `FS` | Dosya yapısı kararları | 08 |
| `SD` | Genel sistem tasarımı kararları | 05 Bölüm II |

| Durum | Anlamı |
|---|---|
| ✅ | **Kullanıcı kararı** (açıkça verildi) |
| ✔ | Çözüldü (belgeler arası uzlaştırma, karar gerektirmedi) |
| 🟡 | **Öneri**, onay bekliyor; öneriyle ilerleniyor |
| 🔴 | Belirli bir fazdan **önce** kapanması gerekiyor (bloklayıcı) |
| ⚪ | Ölçüm veya prototiple kapanacak |

### 1.1 MVP kapsam notu: hukuki süreçler engel değildir

Kullanıcı kararı: bu bir **MVP**; amaç sistemin **çalışıp çalışmadığını görmek**. Hukuki süreçler (hukuki görüş, KVKK/GDPR envanteri, kullanım şartları, silme SLA'sı) **kapsam dışıdır** ve hiçbir fazı bloklamaz. Etki:

| Karar | MVP'de uygulanan |
|---|---|
| D8 robots giriş URL'i | Öneri uygulanır (giriş URL'i bir kez çekilir, bulgu olarak işaretlenir); hukuki onay beklenmez |
| D10 bot adı/bilgi sayfası | Yapılandırma değeri (`BOT_NAME`, `BOT_INFO_URL`), yer tutucu; alan adı şart değil |
| D16 kötüye kullanım politikası | Asgari: kota + hedef-başına sınır + dış istek kaydı; otomatik kısıt/muafiyet süreci yok |
| DM3, DM5, IO4 saklama | 30 gün varsayılan; KVKK envanteri ve silme SLA'sı yok, basit silme komutu yeterli |
| FT5 operatör paneli, gizlilik/silme akışı | MVP dışı; basit yönetim komutu (CLI) |
| Hukuki gözden geçirme, kullanım şartları | Kapsam dışı; ürünleşme kararında yeniden açılır |

**Değişmeyenler:** SSRF koruması, egress kısıtı, bütçe/kota ve prompt injection önlemleri **teknik güvenlik** konularıdır, hukuki değildir; kapsamdan çıkarılmaz. Bunların *sertliği* MVP'yi kimlerin kullanacağına bağlıdır (bkz. §11).

## 2. Kullanıcı kararları (açıkça verilenler)

| Karar | Ne zaman | İşlendiği yer |
|---|---|---|
| Ürün: kullanıcı web sitesi girer, rapor görür | Başlangıç | Tüm belgeler |
| kaynak analizi notları ve `kaynak proje` kaynağı referans; **adım adım doğrula** | Başlangıç | Her belgenin doğrulama matrisi |
| Teknoloji yığını **Python** | D9 turu | 05, 08, 09 |
| İki mod: **site denetimi** (Health Score) ve **sayfa analizi** (Page Score Card), orijinaldeki gibi | D1 | 01 §9 |
| Danışma skoru (LLM) kullanıcıya **gösterilir** | D3 | 01 §4, 03 §3.3 |
| Türkçe: Katman B kapalı, dile bağlı 2 kontrol kapalı | D5 | 01 §4.0 |
| Yerel/staging denetimi **ilk etapta gerekmiyor**, yalnız canlı siteler | L1 | 00 §3.1 |
| GSC (Google görünümü) Faz 3'te | L2 | 00 §3.1 |
| Rapor üzerinde **soru-cevap** ve modül yeniden çalıştırma | L3 | 00 §3.2, 02 §10-11 |
| Skorda LLM nüansı için **telafi yapılmaz** | L4 | 00 §3.1 |
| L5, L6, L7 önerildiği gibi (dönen örneklem, önbellek/BYOK, Türkçe listeler) | L5-L7 | 00 §3.3-3.5 |
| **MVP kullanıcısı: yalnızca kullanıcı** (tek kullanıcı, kimlik doğrulama yok, çok kiracılılık/RLS ertelenir) | MVP profili | 09 §16 |
| **Arayüz: sunucu tarafı HTML (Jinja2)** (IO1) | MVP profili | 06, 09 §16 |
| **Ortam: yalnız yerel makine** (docker-compose: PostgreSQL + Redis); barındırma/IaC ertelenir | MVP profili | 09 §16 |
| **Kod konumu: `seo-analyzer-mvp/seo-analyzer/`** (kendi git deposu) | MVP profili | 08, 09 §16 |
| Hukuki süreçler MVP'de **engel değil**, en iyi çaba planı | MVP profili | Bu belge §1.1 |
| Dosya planı: `02-agent-arhitecture`, `03-rubrik-and-prompts`, `04-data-model`, `05-system-design`, `06-io-schemas`, `07-features`, `08-file-structure` | Klasördeki yer tutucular | Bu numaralandırma |
| Tüm dosyaları bitir; mimari bittikten sonra **faz faz uygula** | Son talimat | 09 |

> **Düzeltme notu:** `docs/architecture/` içinde sizin oluşturduğunuz boş yer tutucu dosyalar vardı; ilk turlarda bunları fark etmedim ve kendi numaralandırmamla ilerledim. Belgeler sizin dosya adlarınıza oturtuldu. `02-agent-arhitecture.md` adındaki yazım hatası (`arhitecture`) **bilerek korundu**; yeniden adlandırmak isterseniz tek komut yeter.

## 3. Çekirdek mimari kararlar (D)

| ID | Karar | Durum | Sonuç / öneri | Belge | En geç ne zaman |
|---|---|---|---|---|---|
| D1 | Birincil çıktı: sayfa mı site mi | ✅ | İki mod, iki skor kartı | 01 §9 | – |
| D2 | Kapsam eşiği ve "Yetersiz veri" davranışı | 🟡 | 60 | 01 §8.4 | Faz 2a kalibrasyonu |
| D3 | Danışma skoru gösterilsin mi | ✅ | Evet, "tahmini" etiketli, trend ve Health Score dışında | 01, 03 | – |
| D4 | İş tipi profilleri ilk sürümde açık mı | 🟡 | Hayır, yalnız etiket | 01 §7.2 | Faz 2a kalibrasyonu |
| D5 | Türkçe heuristikler | ✅ | Katman B ve 2 kontrol kapalı; Katman C açık | 01 §4.0, 03 §13 | – |
| D6 | PSI anahtarı kimden | 🟡 | Bizden (kota izlenir) | 01 §14 | Faz 2a |
| D7 | Örneklem büyüklüğü | 🟡 | **Doğrulanmamış 25, doğrulanmış 50 (üst sınır 200)**, tabakalı, tohumlu. L5 kararı üzerinden dolaylı onay; kesin sayılar kalibrasyonda gözden geçirilir | 05 §9.4 | Faz 2a |
| D8 | Robots: giriş URL'i istisnası | 🟡 | Giriş URL'i bir kez çekilir, diğerleri robots'a tabi | 05 §8.2 | 🔴 Faz 2a (hukuki onay) |
| D9 | Teknoloji yığını | ✅ | Python ≥ 3.11 | 05 §5.2 | – |
| D10 | Bot kimliği ve bilgi sayfası | 🟡 | `SEOAnalyzerBot/1.0` + `/bot` sayfası + IP aralığı; **alan adı gerekli** | 05 §6.2 | 🔴 Faz 1 alfa |
| D11 | Sahiplik doğrulama ve kota katmanları | 🟡 | Doğrulanmamış 25, doğrulanmış 50-200 | 05 §11 | Faz 3 başı (kodda Faz 2a) |
| D12 | Render barındırma | ✔ | **MVP: yerel Playwright**, egress firewall zorunlu değil (tek kullanıcı, yerel); ürünleşmede izole worker + firewall | 05 §5.3 | – |
| D13 | Kuyruk teknolojisi | 🟡 | Arq (asyncio, Redis); alternatifler Celery, Dramatiq | 02 §19 | ⚪ Faz 0 sonu (P2) |
| D14 | LLM sağlayıcı soyutlaması | 🟡 | İlk sürümde tek sağlayıcı (Anthropic), ince arayüz; BYOK aynı sağlayıcı | 02 §19 | Faz 2b |
| D15 | SLO hedefleri | ⚪ | Sayfa p95 < 20/60 sn; site p95 < 3/5 dk (LLM'siz/LLM'li) | 02 §14 | Faz 1 sonu |
| D16 | Kötüye kullanım politikası (eşikler, otomatik kısıt, muafiyet süreci) | 🟡 | Dış istek kaydı, tekrarlayan SSRF reddinde kısıt, bot sayfasında muafiyet | 02 §15 | 🔴 Genel yayın (Faz 2c sonu) |

## 4. Kayıp ve telafi kararları (L)

| ID | Konu | Durum | Karar | Faz |
|---|---|---|---|---|
| L1 | Yerel/staging denetimi | ✅ | Kapsam dışı | – |
| L2 | Googlebot kimliği | ✅ | GSC URL Inspection (doğrulanmış sahipler) + `js_gap` | 3 |
| L3 | Serbest komut | ✅ | Rapor üzerinde Q&A + modül yeniden çalıştırma | 2b |
| L4 | Skorda LLM nüansı | ✅ | **Telafi yapılmaz** | – |
| L5 | Hacim | ✅ | Doğrulanmış 200, dönen örneklem (çekirdek/keşif ayrımı), kullanıcı URL'leri | 2a-3 |
| L6 | LLM maliyeti | ✅ | Önbellek, K≤5 sayfa, küçük model, plan katmanları, BYOK | 2b |
| L7 | Türkçe Katman B | ✅ | Türkçe stopword, filler/CTA listeleri; lisans kontrolü; kök çıkarma ihtiyacı **ölçülecek** | 2b |

## 5. Rubrik ve prompt kararları (R) — belge 03

| ID | Karar | Durum | Öneri |
|---|---|---|---|
| R1 | Band eşikleri (0.67 / 0.34) ve değerler (90/65/35/10) | ⚪ | Başlangıç; kalibrasyonla (belge 01 §13.2) |
| R2 | Girdi üst sınırları (12 000 karakter, 60 bağlantı) | ⚪ | Maliyet/kalite ölçümüyle |
| R3 | Danışma skoru `coverage < 50` eşiği | 🟡 | 50 |
| R4 | A5 (yayın geçmişi) site modunda çekirdek örneklemden türetilsin mi | 🟡 | Evet, Faz 3 |
| R5 | Talimat dili İngilizce mi Türkçe mi | ⚪ | İngilizce talimat, çıktı dili parametre; Faz 2b'de karşılaştırılır |
| R6 | Sayı denetimi (V6) uyarı mı red mi | ⚪ | Uyarı |
| R7 | Dış doğrulama verisi gelince A1-A3 etkinleşsin mi | 🟡 | Evet, ayrı `rubric_version` ile |
| R8 | LLM sağlayıcı/model | ✔ | D14'e bağlı, yapılandırma |

## 6. Veri modeli kararları (DM) — belge 04

| ID | Karar | Durum | Öneri |
|---|---|---|---|
| DM1 | Başlık Health Score tabanı: `all` mı `core` mu | 🟡 | Tek seferlik denetimde `all`, trend yalnız `core`; ikisi de saklanır |
| DM2 | `llm_cache` kiracılar arası paylaşılsın mı | 🟡 | Hayır, kiracı başına |
| DM3 | Ham HTML saklama süresi ve sıkıştırma | 🟡 | 30 gün, `zstd`; hukuki ve maliyet onayı |
| DM4 | UUIDv7 üretici kütüphane | ⚪ | Faz 0'da seçilir |
| DM5 | `findings.evidence` içinde kişisel veri riski | 🟡 | 200 karakter + maskeleme; hukuki inceleme |
| DM6 | `sites` kimliği için Public Suffix List | 🟡 | İlk sürümde yalnız `origin` |
| DM7 | `findings`/`page_fetches` bölümleme | ⚪ | MVP'de yok, ölçümle |
| DM8 | Rapor JSON anlık görüntü mü | 🟡 | Anlık görüntü |
| DM9 | `tier` sitede (`sites.tier`), kullanıcıda değil | ✔ | Kabul edildi; belge 01 §9 ve 05 §9.4 buna göre |
| DM10 | `findings.layer` yalnız `A`/`B`; Katman C bulgu üretmez | ✔ | Kabul edildi; belge 01 §5-6 v0.3'te düzeltildi |
| DM11 | Ek tablolar `page_scores`, `finding_advice` | ✔ | Kabul edildi; belge 03 §7 bunu kullanır |

## 7. API ve rapor kararları (IO) — belge 06

Belge 06'da bu kararlar başlangıçta `D13`-`D20` olarak numaralanmıştı; **IO1-IO8** olarak yeniden adlandırıldı.

| ID | Karar | Durum | Öneri |
|---|---|---|---|
| IO1 | Arayüz teknolojisi | ✅ | **Sunucu tarafı HTML (Jinja2)**; ayrı SPA ürünleşmede değerlendirilir. Backend Python |
| IO2 | PDF motoru (Faz 3) | 🟡 | Playwright `page.pdf()` + ağ kapalı ayrı bağlam |
| IO3 | Paylaşım bağlantısı varsayılanları | 🟡 | 7 gün, en çok 30; `hide_evidence` seçeneği (FT4 ile aynı karar) |
| IO4 | Katman C yeniden çalıştırma ve Q&A için saklanan çıkarılmış alan süresi | 🟡 | 30 gün (DM3 ile uyumlu); sonra `snapshot-expired` |
| IO5 | Q&A kotası | 🟡 | Plan bazlı; başlangıç denetim başına 20 soru |
| IO6 | Rapor dili varsayılanı | 🟡 | Kullanıcı hesabı dili; yoksa TR |
| IO7 | Skor bandı eşikleri (80/50) | ⚪ | Kalibrasyon sonrası; `score_version`'a bağlı |
| IO8 | `GET /rules` herkese açık mı | 🟡 | Evet (şeffaflık) |

## 8. Özellik ve plan kararları (FT) — belge 07

Belge 07'de başlangıçta `D18`-`D25`; **FT1-FT8** olarak yeniden adlandırıldı.

| ID | Karar | Durum | Öneri |
|---|---|---|---|
| FT1 | Plan yapısı: `free`/`pro`/`team` adları ve sayısal sınırlar | ⚪ | Adlar geçici; sınırlar Faz 2a maliyet ölçümünden sonra |
| FT2 | `free` planında LLM (Katman C, Q&A) açık mı | 🟡 | Küçük kotalı veya kapalı; Katman A/B her zaman açık |
| FT3 | Render `free`'de açık mı | 🟡 | Kapalı (maliyet ve güvenlik yüzeyi) |
| FT4 | Paylaşılabilir rapor bağlantısı (F-33) | ✔ | IO3 ile aynı; Faz 2b, imzalı, süreli, `noindex` |
| FT5 | Operatör paneli (F-83) ve gizlilik/silme (F-85) faz ataması | 🟡 | Faz 2c, genel yayın önkoşulu; belge 09 §8'e eklendi |
| FT6 | `unverified` varsayılan örneklem çelişkisi (D7 vs D11) | ✔ | Uzlaştırıldı: 25 / 50, bkz. D7 |
| FT7 | Bulgu geri bildirimi (F-23) süreci | 🟡 | Alfada manuel inceleme; kural bazında sayaç |
| FT8 | GA4 ve CrUX geçmişi hangi fazda | 🟡 | Faz 4+; GSC ile birlikte |

## 9. Dosya yapısı ve sistem tasarımı kararları (FS, SD) — belge 08 ve 05

Belge 08'de `F1`-`F11` olarak numaralanan kararlar **FS1-FS11** olarak yeniden adlandırıldı (özellik kimlikleri `F-xx` ile karışmasın diye). Belge 05 Bölüm II'nin açık kararları **SD** önekiyle.

| ID | Karar | Durum | Sonuç / öneri |
|---|---|---|---|
| FS1 | Fetch/Render worker'ları DB'ye erişmesin; sonuçları yalnız-yazma depolama + Redis akışıyla iletsin, DB'ye Control yazsın | ✔ | Kabul edildi, belge 02 §3.2'de tasarlandı; Faz 0 P2 akış teslimini de sınar |
| FS2 | E2E için `FixtureFetcher` protokol enjeksiyonu (üretimde test izin listesi yok) | ✔ | Kabul edildi; belge 09 Faz 0 teslimat 0.9 |
| FS3 | `third_party/kaynak_proje/` kopya mı submodule mu | 🟡 | Sabitlenmiş kopya + `NOTICE` |
| FS4 | Tek paket (`seoa`) mı, çoklu paket (uv workspace) mı | 🟡 | Tek paket (Faz 0-2); sınırlar import-linter ile |
| FS5 | Tek çok-aşamalı Dockerfile mı, worker başına ayrı mı | 🟡 | Tek, çok hedefli |
| FS6 | Mesaj kataloğu (`i18n`) nerede | 🟡 | Paket içinde (`report/i18n/`) |
| FS7 | Egress vekili ürünü | ⚪ | Faz 0 P3'te seçilir (SD2 ile aynı karar) |
| FS8 | Python sürüm matrisi | 🟡 | 3.11 + 3.12; 3.14 bağımlılıklara göre |
| FS9 | Kural verisi biçimi | 🟡 | JSON + JSON Schema |
| FS10 | Saflık zorlaması | 🟡 | import-linter **ve** AST testi birlikte |
| FS11 | Belge 09 teslimat 0.3 ifadesinin düzeltilmesi | ✔ | Yapıldı: politika testleri adaptörle taşınır, pin testleri yeniden yazılır |
| SD1 | Barındırma platformu | ✔ | **MVP: yerel makine**; barındırma ürünleşmede seçilir |
| SD2 | Egress proxy ürünü | ⚪ | Faz 0 P3 (FS7 ile aynı) |
| SD3 | Sır yönetimi | 🟡 | Yönetilen sır deposu + zarf şifreleme anahtarı; Faz 1 |
| SD4 | Kod olarak altyapı aracı | ✔ | MVP'de yok (yalnız docker-compose) |
| SD5 | Veritabanı yüksek erişilebilirlik ve yedekleme düzeyi | 🟡 | Yönetilen PostgreSQL, zaman noktası kurtarma; genel yayın |

### 9.1 Doğrulama sırasında düzeltilen hatalar (şeffaflık)

Belgeler yazılırken ve çapraz kontrolde şu **yanlış iddialar** yakalanıp düzeltildi:

| Yanlış iddia | Doğrusu | Düzeltilen yer |
|---|---|---|
| "`test_hostile_inputs.py` SSRF testidir" | Agentic/robots, JSON derinliği, Keywords Everywhere ve Lighthouse ayrıştırıcılarının bozuk girdi testidir | 00 §4, 05 §5.2/§13, 09 §4.1 |
| "SSRF testleri yeni resolver'a değişmeden uyar" | `socket.getaddrinfo` yamasına bağlıdır (62/41/10 geçiş); yeniden yazılır | 00 §4, 05, 09 |
| "Kaynak fixture'larıyla parity" | `tests/fixtures/` yalnız 2 alakasız dosya; HTML'ler test dosyalarında satır içi | 00 §4, 09 |
| "Kaynak crawl yapar (500 sayfa)" | Crawler kodda yok, yalnız prompt metni | 05 §2 |
| "`fetch_page.py` UA rotation yapar (CLAUDE.md)" | Yok; tek sabit UA ve `--googlebot` | `kaynak analizi notları 05` |
| "Redirect sınırı 3 (SKILL.md)" | Kodda 5 | 05 §2 |
| "D7 varsayılan 50 sayfa" ile "D11 doğrulanmamış 25" çelişkisi | Katmana bağlı: 25 / 50 (üst sınır 200) | 05 §9.4, 09 |
| Fetch/Render "sır yok" ama sonuç yazma yolu tanımsız | Sonuç alıcı deseni (nesne depolama + Redis akışı) | 02 §3.2 |
| "`SafeResolver` tek başına SSRF'yi kapatır" | `aiohttp` IP-literal URL'lerde resolver'ı çağırmaz (P1 deneyi); `check_url` ön doğrulaması ve elle redirect şart | 05 §5.2, `docs/prototypes/P1-safe-resolver.md` |
| "Playwright `route` handler'ı SSRF için yeterli" (kaynak kaynak proje dahil) | Chromium yönlendirmeleri iç ağında izler; handler ara adımları görmez, 302 ile gizli sunucuya erişilebildi. `route.fetch(max_redirects=0)` ile manuel zincir izleme gerekti | 05 §5.3, `src/seoa/render/browser.py` |
| "Alıntı doğrulaması modelin gördüğü metinle aynı biçimde" | `chrome_link` alanı için doğrulanan metin (`anchor\nhref`) ile modele gösterilen metin (`[footer] anchor -> href`) farklıydı; model doğru bulduğu **Türkçe** "Gizlilik Politikası" sinyalini sessizce `unclear`'a düşürülüyordu. Gerçek API testi yakaladı; doğrulama artık gösterilen metinle birebir | `src/seoa/llm/input.py`, `tests/unit/test_llm_chrome_quote.py` |
| "Q&A bağlamı yalnız Critical/High bulguları + anahtar kelimeleri alır" | Hiç Critical/High yoksa ve soru Türkçe ise bağlama bulgu girmiyor, "raporda yok" cevabı dönüyordu. Artık soru ne olursa olsun şiddet sırasıyla ilk 8 bulgu bağlamda | `src/seoa/llm/qa.py`, `tests/unit/test_llm_qa_context.py` |
| "Rapor metinleri kural kaydından gelir (içe aktarma sırasından bağımsız)" | Golden dosya, kayıtlar boşken üretilmiş ve kısa yedek metinler taşıyordu; ayrıca API süreci kuralları yüklemeden rapor kurabilirdi. `load_all_rules()` rapor oluşturucuda garanti edildi | `src/seoa/checks/__init__.py`, `report/builder.py` |
| "Skor yalnızca ceza çıkarır (şiddet tavanlı)" | Geçen kontroller görünmediği için "40 kontrolden 38'i geçti" bilgisi kayboluyor ve skor neyin ölçüldüğünü anlatmıyordu. Skor v2 (`mvp-0.2`): kategori skoru = uygulanabilir kontrollerin şiddetle ağırlıklı geçen payı; kontrol tablosu her kategoride görünür; ölçülemeyen kural paydadan çıkar, geçti sayılmaz; aynı sorunun varyantları (TLS, HSTS, CSP, sitemap, CWV) tek kontrol sayılır | `docs/architecture/11-scoring-v2-and-site-analysis.md`, `src/seoa/scoring/score.py` |
| "Skor, sitenin aramadaki başarısını gösterir" | Skor yalnızca teknik ve sayfa içi hijyen ölçer; indeksleme, sıralama, geri bağlantı, saha hız verisi ölçülmez. Ad "Teknik ve Sayfa İçi Sağlık Skoru" oldu, raporda "Bu skor neyi ölçmez" kutusu var | belge 11 §2.3 |
| "Kod `seo-analyzer/` alt dizininde" | Kullanıcı yapıyı kökte düzleştirdi; kod depo kökünde | 09 §16.1 |
| Proje kökünde `ruff` çalıştırmak güvenli | `kaynak/` altındaki 166 dosyayı biçimlendirdi (yalnız biçim; `HEAD`+`ruff format` ile birebir doğrulandı). Geri alma izin sınıflandırıcısınca engellendi; `ruff` artık `extend-exclude` ile kısıtlı | 09 §16.1 |
| Boş yer tutucu dosyaların fark edilmemesi | Belgeler kullanıcı planındaki adlara oturtuldu | Bu günlük §2 |

## 10. Faz kapıları: hangi karar hangi fazdan önce kapanmalı

| Faz | Kapanması gereken kararlar |
|---|---|
| **Faz 0 sonu** | D13 (kuyruk, P2), D12 (render, P3), SD1 (barındırma), SD2/FS7 (egress proxy), SD4 (IaC), DM4 |
| **Faz 1 alfa** | **D10** (bot adı, alan adı), IO1 (arayüz teknolojisi), SD3 (sır yönetimi), D15 ölçüm planı |
| **Faz 2a** | **D8** (robots istisnası, hukuki), D2, D4, D6, D7 kalibrasyonu, FT1 maliyet ölçümü |
| **Faz 2b** | D14, IO3-IO5, FT2, FT3, DM3/IO4 (saklama), L7 lisans kontrolü, R1-R5 prototipi |
| **Genel yayın (2c sonu)** | **D16** (kötüye kullanım), FT5 (operatör paneli, gizlilik/silme), SD5 (DB yedekleme), hukuki gözden geçirme (KVKK/kullanım şartları) |
| **Faz 3** | D11 (doğrulama akışı), IO2 (PDF), FT8, R4, R7 |

## 11. Bekleyen kullanıcı onayları (özet)

> MVP notu (§1.1): hukuki nitelikli maddeler (2, 3, 5) **artık bekleme gerektirmez**, öneriyle uygulanır. Aşağıda işi gerçekten etkileyen sorular kalır: MVP kullanıcıları, arayüz, çalışma ortamı, kod konumu.

Önerilerle ilerleniyor, ama **açık onay** gerektirenler (orijinal liste):

1. **D10:** bot adı ve **alan adı** (Faz 1 alfa öncesi şart).
2. **D8:** robots giriş URL'i istisnası (hukuki görüş).
3. **D16:** kötüye kullanım politikası eşikleri (genel yayın öncesi).
4. **D11:** sahiplik doğrulama yöntemi (DNS TXT / meta / dosya) ve katman sınırları.
5. **DM3/IO4:** saklama süresi (30 gün) ve KVKK/GDPR yaklaşımı.
6. **FT1-FT3:** plan adları, sınırlar, `free`'de LLM/render.
7. **IO1:** arayüz teknolojisi (sunucu HTML mi, ayrı SPA mı).
