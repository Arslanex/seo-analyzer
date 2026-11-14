# 07. Özellik Kataloğu

> Durum: **Taslak v0.1** · Girdi: belge 00, 01, 02, 05, 09 ve `kaynak analizi notları 04-skills-catalog.md`
> İşaretler: `[K]` kaynak projeden alındı · `[B]` bizim kararımız · `[?]` açık karar · `[doğrulandı]` kaynak kodla/dosyayla kontrol edildi
> **Belge numaraları nihaidir:** 00 capability-parity · 01 evaluation-system · 02 agent-arhitecture (iş hattı, worker'lar, LLM katmanı) · 03 rubrik-and-prompts · 04 data-model · 05 system-design (fetch, crawl, SSRF) · 06 io-schemas (API + `audit.json`) · 07 features (bu belge) · 08 file-structure · 09 implementation-roadmap · 10 decision-log. Diskte bazı dosyalar henüz eski adlarıyla durabilir.
> Bu belgede **kesin fiyat ve tarih yoktur.** Plan adları (`free`, `pro`, `team`) geçicidir; sayısal sınırlar yalnız önceki belgelerde kararlaştırılmışsa verilir, aksi halde `[?]` işaretlidir.

---

## 1. Ürün özeti

### 1.1 Ne yapar
Kullanıcı internetteki **canlı** bir web sitesinin (veya tek bir sayfasının) adresini girer. Sistem siteyi güvenli biçimde çeker, deterministik kurallarla ölçer, **tekrarlanabilir** bir skor ve kanıtlı bulgu listesi üretir, LLM ile yorum ve öneri ekler ve sonucu rapor olarak sunar. Kullanıcı raporu inceler, rapora soru sorar, ilgili modülü yeniden çalıştırır ve geçmişle karşılaştırır.

### 1.2 Hedef kullanıcılar `[B]`
| Kullanıcı | İhtiyaç | Öne çıkan özellikler |
|---|---|---|
| Site sahibi / küçük işletme | "Sitemde ne bozuk, önce neyi düzeltmeliyim?" | Sayfa/site denetimi, öncelikli plan, Türkçe rapor |
| Serbest SEO danışmanı | İlk görüşmede hızlı, kanıtlı rapor | Rapor paylaşımı, PDF, Q&A |
| Ajans / şirket içi SEO ekibi | Müşteri siteleri için düzenli izleme | Doğrulanmış site, izleme, drift uyarıları, API |
| Geliştirici | Yayın sonrası regresyon yakalama | JSON çıktı, API, drift |

### 1.3 Değer önerisi (kaynak projeye göre fark) `[B]`
- **Tekrarlanabilir skor:** skoru kod hesaplar, LLM değil (belge 01 P1). kaynak projede Health Score'u LLM üretir `[doğrulandı: belge 01 §12]`.
- **Dürüst kapsam:** ölçülmeyen şeye puan verilmez; kapsam ve güven her raporda görünür (belge 01 §8).
- **Kanıtlı yorum:** LLM çıktısı sayfa metninden alıntıyla doğrulanır (belge 02 §9).
- **Ürün olarak sunulur:** kaynak proje bir Claude Code eklentisidir; biz kullanıcıya web arayüzü, API, geçmiş ve izleme sunarız.

### 1.4 Kapsam sınırı
Yalnızca **internetteki canlı sunucular** (belge 00 §3.1, L1). Yerel/staging/özel ağ hedefleri yoktur.

## 2. Erişim modeli

İki bağımsız eksen vardır:

| Eksen | Değerler | Neyi belirler |
|---|---|---|
| **Site katmanı (tier)** | `unverified` · `verified` | Örneklem tavanı, tarama hızı, izleme erişimi (belge 05 D11) |
| **Plan** | `free` · `pro` · `team` (geçici adlar) | LLM kotası, Q&A, PDF, API, BYOK, denetim sayısı |

Etkili sınır = ikisinin **daha kısıtlısı**. Örnek: `team` planında olup siteyi doğrulamamış kullanıcı yine 25 sayfa tavanındadır.

**Örneklem sınırları (belge 05 D7 + D11, tutarlılaştırılmış `[B]`):**

| Site katmanı | Site modunda örneklem | Not |
|---|---|---|
| `unverified` | **en çok 25 sayfa**, düşük hız, günlük kota | Kötüye kullanım ve hedefe yük önlemi |
| `verified` | **varsayılan 50, üst sınır 200** | Daha yüksek hız, izleme |
| Sayfa modu | 1 sayfa | Her iki katman |

---

## 3. Özellik haritası

Her özellik: **kullanıcı hikâyesi**, tasarım belgesi, **faz** (belge 09: 0, 1, 2a, 2b, 2c, 3, 4+), bağımlılık, **ölçülebilir kabul ölçütü**, erişim, kaynak proje karşılığı. Kabul ölçütlerindeki sayısal hedefler önceki belgelerden alınmıştır; yeni olanlar `[?]` işaretlidir.

### Grup A: Giriş ve denetim modları

#### F-01 Sayfa analizi
- **Hikâye:** Tek bir URL girip o sayfa için skor kartı ve bulgu listesi almak istiyorum.
- **Tasarım:** belge 01 §9, belge 05 §3-§6, belge 02 §4.
- **Faz:** 1 · **Bağımlılık:** F-03, F-10, F-20, F-30
- **Kabul:** Page Score Card 5 kategoriyle üretilir (Sayfa içi, İçerik, Teknik, Schema, Görseller); aynı girdi → aynı skor; LLM'siz p95 < 20 sn (belge 02 §14).
- **Erişim:** tüm plan ve katmanlar · **kaynak proje:** `/seo page` (`seo-page`) `[K]`

#### F-02 Site denetimi
- **Hikâye:** Sitemin geneli için tek bir sağlık skoru ve öncelikli sorun listesi istiyorum.
- **Tasarım:** belge 01 §9, belge 05 §9, belge 02 §4.
- **Faz:** 2a · **Bağımlılık:** F-01, F-06, F-07, F-17
- **Kabul:** Health Score 7 kategoriyle; kapsam raporu (planlanan/çekilen/render edilen/atlanan); 50 sayfalık örneklem p95 < 3 dk (LLM'siz); hedef host'un gördüğü istek hızı sınır altında (yük testi).
- **Erişim:** tüm planlar; sayfa tavanı site katmanına bağlı (§2) · **kaynak proje:** `/seo audit` (`seo-audit`) `[K]`

#### F-03 URL girişi, normalizasyon ve ret mesajları
- **Hikâye:** `example.com` yazmam yeterli olsun; geçersiz veya güvensiz bir adres verirsem nedenini anlayayım.
- **Tasarım:** belge 05 §4-§5.
- **Faz:** 1 · **Bağımlılık:** `safefetch` (Faz 0)
- **Kabul:** şemasız giriş `https://` ile tamamlanır; özel IP, `localhost`, metadata hostname'leri, `user@host`, ondalık/hex IP reddedilir ve kullanıcıya **anlaşılır, bilgi sızdırmayan** mesaj gösterilir; kaynağın hostile testleri yeni uygulamaya karşı yeşil.
- **Erişim:** hepsi · **kaynak proje:** `url_safety.py` politikası `[K, doğrulandı]`

#### F-04 Denetim ilerleme akışı
- **Hikâye:** Denetim sürerken neyin yapıldığını göreyim; sayfayı kapatsam da denetim sürsün.
- **Tasarım:** belge 02 §13 (SSE), belge 06.
- **Faz:** 1 · **Bağımlılık:** F-01
- **Kabul:** aşama geçişlerinde olay yayınlanır; istemci yeniden bağlanınca `Last-Event-ID` ile kaldığı yerden devam eder; sayfa kapatılınca denetim tamamlanır.
- **Erişim:** hepsi · **kaynak proje:** yok (terminal çıktısı) `[B]`

#### F-05 Denetim iptali
- **Hikâye:** Yanlış URL girdiysem denetimi durdurayım.
- **Tasarım:** belge 02 §14.
- **Faz:** 1 · **Bağımlılık:** F-04
- **Kabul:** iptal sonrası yeni dış istek başlamaz; uçuştaki istekler bırakılır; durum `canceled`; kullanılan kota geri iade edilmez ama harcanan kadar yazılır `[?]`.
- **Erişim:** hepsi · **kaynak proje:** yok `[B]`

#### F-06 Örneklem, kapsam raporu ve kullanıcı tanımlı URL'ler
- **Hikâye:** Hangi sayfaların incelendiğini ve neden olduğunu görmek, ayrıca önemli sayfalarımı her denetime eklemek istiyorum.
- **Tasarım:** belge 05 §9, belge 00 §3.3.
- **Faz:** 2a · **Bağımlılık:** keşif (sitemap, iç linkler), şablon kümeleme
- **Kabul:** aynı tohum → aynı örneklem; **çekirdek** (sabit) ve **keşif** (dönen) örneklem ayrı etiketli; çekirdek skor ardışık iki çalıştırmada değişmez; şablon başına en az 1, en çok N/3 sayfa; kullanıcı tanımlı URL'ler scope içinde ve tavanlı.
- **Erişim:** hepsi (tavan site katmanına bağlı) · **kaynak proje:** crawl yalnız prompt metni, kodu yok `[doğrulandı: belge 05 §2]`

#### F-07 SPA render ve `js_gap`
- **Hikâye:** JavaScript ile oluşturulan içeriğin arama botlarına görünüp görünmediğini bilmek istiyorum.
- **Tasarım:** belge 05 §7, belge 01 §7.1 (AI arama hazırlığı).
- **Faz:** 2a · **Bağımlılık:** render worker, egress firewall (belge 09 P3), F-84 bayrağı
- **Kabul:** `_is_spa` eşikleriyle (400/100 karakter) yalnız gerektiğinde render; en çok K=5 sayfa; `js_gap` eşikleri (%30/25 kelime, %30/3 link) kaynakla aynı; render worker'dan özel aralığa bağlantı **ağ seviyesinde** reddedilir (dağıtım testi).
- **Erişim:** `pro`/`team` `[?]` (maliyet ve güvenlik yüzeyi nedeniyle `free`'de kapalı olabilir) · **kaynak proje:** `render_page.py` `[K, doğrulandı]`

### Grup B: Değerlendirme

#### F-10 Kategori skorları ve genel skor (kod hesaplı)
- **Hikâye:** Sitemin durumunu tek sayıyla ve kategori kırılımıyla görmek, bu sayıya güvenebilmek istiyorum.
- **Tasarım:** belge 01 §8.
- **Faz:** 1 · **Bağımlılık:** F-20, kural kaydı
- **Kabul:** saf fonksiyon; **bulgu eklemek skoru artıramaz** (özellik testi); `score_version` her raporda; ağırlıklar yeniden normalize edilir; Spearman ≥ 0.7 kalibrasyon hedefi (Faz 2a çıkış kriteri).
- **Erişim:** hepsi · **kaynak proje:** Health Score (LLM yargısı) → **dönüştürüldü** `[K, belge 00 §2.2]`

#### F-11 Kapı (gate) banner'ı
- **Hikâye:** Site indekslenemiyorsa yüksek skor görmeyeyim; neden sınırlandığını anlayayım.
- **Tasarım:** belge 01 §8.3.
- **Faz:** 1 · **Bağımlılık:** F-10
- **Kabul:** ana URL'de `noindex`/`noindex-header`, `status ≥ 400`, geçersiz TLS → tavan 40; `canonical-points-elsewhere` veya tüm site robots engeli → tavan 70; banner "Skor şu nedenle sınırlandı: `<id>`" der.
- **Erişim:** hepsi · **kaynak proje:** yok (kaynakta kapı kavramı yok) `[B]`

#### F-12 Kapsam yüzdesi ve "Yetersiz veri"
- **Hikâye:** Raporun ne kadarının gerçekten ölçüldüğünü bilmek istiyorum.
- **Tasarım:** belge 01 §8.4.
- **Faz:** 1 · **Bağımlılık:** F-14
- **Kabul:** `kapsam ≥ 60` → sayı + "Kapsam %X"; `kapsam < 60` → sayı **gösterilmez**, "Yetersiz veri" yazılır; eşik yapılandırılabilir (D2).
- **Erişim:** hepsi · **kaynak proje:** backlink 4/7 faktör kapısından genelleştirildi `[K, doğrulandı: test_backlink_score_gate.py]`

#### F-13 Güven etiketi
- **Hikâye:** Skorun ne kadar güvenilir olduğunu görmek istiyorum.
- **Tasarım:** belge 01 §8.5.
- **Faz:** 1 · **Bağımlılık:** F-06 (örneklem), F-14
- **Kabul:** yüksek/orta/düşük kuralları kodla: tümü Katman A ve veri tam → yüksek; örneklem < 30 sayfa veya Katman B düzelticisi etkin → en çok orta; büyük bölüm `not_checked` veya render başarısız → düşük.
- **Erişim:** hepsi · **kaynak proje:** yok `[B]`

#### F-14 "Ölçülmedi" kartları
- **Hikâye:** Neyin neden ölçülemediğini (PSI yok, render başarısız, dil desteklenmiyor) açıkça göreyim.
- **Tasarım:** belge 01 §5, belge 05 §12 (gerekçe kodları).
- **Faz:** 1 · **Bağımlılık:** kural kaydı `requires`
- **Kabul:** her `not_checked` kaydı bir gerekçe koduna ve kullanıcı metnine eşlenir; ölçülmeyen kategori gri kart olur; kontrol "geçti" sayılmaz.
- **Erişim:** hepsi · **kaynak proje:** `page_checks.not_checked` `[K, doğrulandı]`

#### F-15 Danışma skoru (E-E-A-T)
- **Hikâye:** İçeriğimin deneyim/uzmanlık/otorite/güven sinyallerine dair tahmini bir değerlendirme istiyorum, ama bunun kesin bir ölçüm olmadığını bilerek.
- **Tasarım:** belge 01 §4, belge 02 §9, belge 03 (rubrik).
- **Faz:** 2b · **Bağımlılık:** Katman C, önbellek, bütçe
- **Kabul:** **genel skora girmez** ve trend grafiğinde yer almaz (test); "tahmini" etiketi; rubrik bantları sabit eşleme; her gözlem sayfa metninde birebir alıntıyla desteklenir, aksi halde reddedilir; model ve rubrik sürümü kayıtlı.
- **Erişim:** `pro`/`team`; `free` için sınırlı veya kapalı `[?]` · **kaynak proje:** `seo-content` E-E-A-T (20/25/25/30, "Google'ın ağırlıkları değil" notu) `[K, doğrulandı: agents/seo-content.md]`

#### F-16 Sürümlü kural ve skor
- **Hikâye:** Skor yöntemi değiştiğinde eski ve yeni raporların neden kıyaslanamadığını anlayayım.
- **Tasarım:** belge 01 P5, belge 04.
- **Faz:** 1 · **Bağımlılık:** `rule_versions`, `score_versions`
- **Kabul:** her rapor `rule_version` ve `score_version` taşır; sürüm farkı varsa trend çizilmez, yalnız bulgu farkı gösterilir; eski rapor yeniden hesaplanmaz.
- **Erişim:** hepsi · **kaynak proje:** yok `[B]`

#### F-17 Performans (PSI/CrUX)
- **Hikâye:** Core Web Vitals durumumu görmek istiyorum.
- **Tasarım:** belge 01 §7.1, belge 05 §14 (bizim PSI anahtarımız, D6).
- **Faz:** 2a · **Bağımlılık:** PSI anahtarı ve kota
- **Kabul:** LCP ≤ 2.5 sn / INP ≤ 200 ms / CLS ≤ 0.1 "iyi", > 4 sn / > 500 ms / > 0.25 "kötü" `[doğrulandı: pagespeed_check.CWV_THRESHOLDS]`; yalnız INP anılır (FID yok); anahtar/kota yoksa kategori **"ölçülmedi"** (`psi-unavailable`).
- **Erişim:** hepsi (PSI maliyeti bizde, kota planla sınırlı `[?]`) · **kaynak proje:** `seo-performance`, `pagespeed_check.py` `[K]`

#### F-18 AI arama hazırlığı
- **Hikâye:** Sitemin AI arama motorları tarafından erişilebilir ve alıntılanabilir olup olmadığını görmek istiyorum.
- **Tasarım:** belge 01 §7.1; belge 09 Faz 2a (deterministik), Faz 2b (yorum).
- **Faz:** 2a (robots AI bot erişimi, `js_gap`, yapı), 2b (yorum) · **Bağımlılık:** F-07
- **Kabul:** robots ayrıştırması RFC 9309 grup seçimiyle (adlandırılmış grup `*` yerini alır, miras yok) `[doğrulandı: agentic_check.parse_robots]`; eğitim/arama botları ayrı raporlanır (GPTBot'un ChatGPT Search crawler'ı olmadığı notu `[doğrulandı: agents/seo-geo.md]`); llms.txt isteğe bağlı sinyal olarak, Google'ın yok saydığı notuyla.
- **Erişim:** hepsi (yorum: bkz. F-15) · **kaynak proje:** `seo-geo`, `seo-agentic` `[K]`

### Grup C: Bulgular ve aksiyon planı

#### F-20 Bulgu listesi (kanıt, öncelik, filtre)
- **Hikâye:** Her bulgunun ne olduğunu, kanıtını, önemini ve nasıl düzelteceğimi göreyim; filtreleyeyim.
- **Tasarım:** belge 01 §6, belge 06.
- **Faz:** 1 · **Bağımlılık:** kural kaydı
- **Kabul:** her bulgu `id`, `severity`, `layer`, `evidence` (≤ 200 karakter, kaçışlanmış), `heuristic` etiketi taşır; heuristik bulgu "Google kuralı değil" notunu gösterir; severity/kategori/sayfa filtresi; 47 `page_checks` kontrolü aynı id ve severity ile (parity testi).
- **Erişim:** hepsi · **kaynak proje:** `page_checks.py` (47 kontrol: Critical 2 / High 6 / Medium 24 / Low 15) `[K, doğrulandı]`

#### F-21 Aksiyon planı (4 faz, çaba/etki)
- **Hikâye:** Neyi hangi sırayla düzelteceğimi anlatan bir plan istiyorum.
- **Tasarım:** belge 02 §9.1 (synthesize), belge 06.
- **Faz:** Faz 1'de severity sıralı öncelik listesi; **4 fazlı plan 2b** · **Bağımlılık:** F-20, kural kaydında `effort`/`impact` varsayılanları
- **Kabul:** plan fazları Hafta 1 / Hafta 2-3 / Ay 2 / Sürekli; `effort` ve `impact` **kural kaydından deterministik** gelir, LLM yalnız metni yazar; `depends_on` döngü içermez (test).
- **Erişim:** hepsi · **kaynak proje:** `audit-data.json` `action_plan.phases` (effort/etki yapılandırılmış değil) `[K, doğrulandı: belge 08]`

#### F-22 Öne çıkan bulgular ve hızlı kazanımlar
- **Hikâye:** İlk bakışta en önemli 5 sorunu ve en kolay 5 kazanımı göreyim.
- **Tasarım:** belge 06 (rapor özeti).
- **Faz:** 2b (Faz 1'de severity'ye göre ilk 5) · **Bağımlılık:** F-21
- **Kabul:** seçim kuralı deterministik (severity × etki ÷ çaba); LLM yalnız açıklama metni yazar; her öğe bir `finding id`'ye bağlıdır.
- **Erişim:** hepsi · **kaynak proje:** `summary.top_findings`, `quick_wins` `[K]`

#### F-23 Yanlış pozitif bildirimi
- **Hikâye:** Hatalı bir bulguyu işaretleyip bildirebileyim.
- **Tasarım:** belge 09 §5.5 (alfa riski), belge 04.
- **Faz:** 1 · **Bağımlılık:** F-20
- **Kabul:** bulgu başına bildirim (id, URL, kullanıcı notu); bildirimler kural bazında toplanır; kural başına yanlış pozitif sayacı ürün metriğine yansır.
- **Erişim:** hepsi · **kaynak proje:** yok `[B]`

#### F-24 Schema doğrulama
- **Hikâye:** Sayfamdaki yapılandırılmış verinin geçerli olup olmadığını öğreneyim.
- **Tasarım:** belge 09 Faz 1.
- **Faz:** 1 · **Bağımlılık:** `parse_html` JSON-LD ayrıştırma
- **Kabul:** bozuk JSON-LD (`invalid-jsonld`) tespit edilir; tip/zorunlu alan doğrulaması; deprecated tipler işaretlenir (HowTo asla önerilmez); mevcut FAQPage **Info** seviyesinde raporlanır ve kaldırılması önerilmez `[doğrulandı: skills/seo/SKILL.md Quality Gates]`.
- **Erişim:** hepsi · **kaynak proje:** `seo-schema`, `hooks/validate-schema.py` `[K]`

#### F-25 Schema üretimi (kopyala-yapıştır JSON-LD)
- **Hikâye:** Eksik schema için hazır, doğrulanmış JSON-LD kodunu alıp sayfama ekleyeyim.
- **Tasarım:** belge 00 §2.3, belge 09 Faz 2c.
- **Faz:** 2c · **Bağımlılık:** F-24, `schema_generate.py` portu
- **Kabul:** üretilen her örnek kendi doğrulayıcımızdan geçer; placeholder içermez; deprecated tip üretilmez; yeni FAQPage Google SERP faydası iddiasıyla önerilmez; kaynak testleri yeşil. **Hangi tiplerin portlanacağı taşıma sırasında kaynaktan doğrulanır** `[?]`.
- **Erişim:** `pro`/`team` `[?]` · **kaynak proje:** `/seo schema` (algılama, doğrulama, üretim), `scripts/schema_generate.py` `[K, doğrulandı: varlık; tip listesi doğrulanmadı]`

### Grup D: Rapor biçimleri

#### F-30 HTML rapor (TR/EN)
- **Hikâye:** Raporu tarayıcıda, Türkçe veya İngilizce okuyayım.
- **Tasarım:** belge 06 (arayüz bilgi mimarisi).
- **Faz:** 1 · **Bağımlılık:** `audit.json` şeması
- **Kabul:** yönetici özeti, skor kartları (kapsam+güven), kapı banner'ı, kategori bölümleri, bulgu tablosu, metodoloji ve sınırlar; **5 severity seviyesi renk dışında ikon/metinle de ayırt edilir** (kaynak projede hepsi aynı amber `[doğrulandı: belge 08]`); sayfadan gelen metin kaçışlanır (XSS testi); CSP.
- **Erişim:** hepsi · **kaynak proje:** `google_report.py` HTML çıktısı `[K]`

#### F-31 JSON dışa aktarma
- **Hikâye:** Rapor verisini başka araçlarda kullanmak için JSON olarak alayım.
- **Tasarım:** belge 06 (`audit.json`).
- **Faz:** 1 · **Bağımlılık:** F-30
- **Kabul:** çıktı JSON Schema'ya uyar (doğrulayıcı testi); `schema_version` taşır.
- **Erişim:** hepsi (programatik erişim `pro`/`team`) · **kaynak proje:** `audit-data.json` `[K]`

#### F-32 PDF rapor
- **Hikâye:** Müşteriye göndermek için PDF alayım.
- **Tasarım:** belge 06, belge 09 Faz 3.
- **Faz:** 3 · **Bağımlılık:** F-30, rapor kalite kapısı
- **Kabul:** kalite kapısı `PASS` olmadan kullanıcıya sunulmaz (kırık görsel, boş bölüm, çift tablo, taşan tablo, sayfa sınırı); HTML her zaman çalışır, PDF bağımlılığı yoksa zarif bozulma.
- **Erişim:** `pro`/`team` · **kaynak proje:** `google_report.py --type full`, `_review_pdf` `[K, doğrulandı: skills/seo-audit/SKILL.md]`

#### F-33 Paylaşılabilir rapor bağlantısı
- **Hikâye:** Raporu hesabı olmayan birine göstermek için bağlantı paylaşayım.
- **Tasarım:** belge 06 (imzalı URL, süre).
- **Faz:** 2b `[?]` (yol haritasında açık yer yok) · **Bağımlılık:** F-30
- **Kabul:** imzalı ve süreli URL; iptal edilebilir; paylaşılan görünümde BYOK/kota/hesap bilgisi yok; arama motorlarına kapalı (`noindex`).
- **Erişim:** `pro`/`team` `[?]` · **kaynak proje:** yok `[B]`

### Grup E: Etkileşim

#### F-40 Rapor üzerinde soru-cevap
- **Hikâye:** Raporda anlamadığım bir bulgu hakkında soru sorayım.
- **Tasarım:** belge 02 §10, belge 00 §3.2.
- **Faz:** 2b · **Bağımlılık:** Katman C altyapısı, kota
- **Kabul:** yalnız kayıtlı rapordan cevap, **yeniden fetch yok, ağ erişimi yok**; her cevap `finding id`/URL atfı taşır ve atıfsız iddia reddedilir; rapor dışı soru nazikçe reddedilir; denetim başına soru ve token tavanı; `evidence` içindeki talimat yok sayılır (injection testi).
- **Erişim:** `pro`/`team`; `free` için küçük kota veya kapalı `[?]` · **kaynak proje:** yok (kaynakta eşleniği bulunamadı) `[B]`

#### F-41 Modül yeniden çalıştırma
- **Hikâye:** Düzeltme yaptıktan sonra yalnız ilgili modülü tekrar çalıştırayım.
- **Tasarım:** belge 02 §11.1, belge 00 §3.2.
- **Faz:** 2b · **Bağımlılık:** `parent_audit_id`, saklanan HTML gövdeleri
- **Kabul:** **yeni** denetim satırı üretir, eskisini değiştirmez; Katman A/B saklanan gövdeler üzerinde yeniden fetch yapmadan çalışır (saklama süresi içinde), gövde silindiyse yeniden fetch; Katman C kotadan düşer, girdi hash'i aynıysa önbellekten.
- **Erişim:** `pro`/`team`; deterministik modüller `free`'de de `[?]` · **kaynak proje:** her komutu ayrı çalıştırma (`/seo technical`, `/seo schema` ...) → dönüştürüldü `[K]`

#### F-42 Denetim geçmişi
- **Hikâye:** Daha önce yaptığım denetimleri listeleyip açayım.
- **Tasarım:** belge 04, belge 06 (`GET /v1/sites/{id}/history`).
- **Faz:** 2a · **Bağımlılık:** çok kiracılılık
- **Kabul:** kiracı izolasyonu testi (başka kiracının denetimi görünmez/okunamaz); sayfalama; filtre (site, mod, durum).
- **Erişim:** hepsi (saklama süresi plana bağlı `[?]`) · **kaynak proje:** yok (dosya sistemi `{domain}-audit/`) `[B]`

#### F-43 Skor trendi
- **Hikâye:** Düzeltmelerimin skoru nasıl etkilediğini zaman içinde göreyim.
- **Tasarım:** belge 01 §10, belge 00 §3.3.
- **Faz:** 3 · **Bağımlılık:** F-06 (çekirdek örneklem), F-16
- **Kabul:** trend **yalnız çekirdek örneklem skorundan** ve **aynı `score_version` içinde** çizilir; sürüm değişince çizgi kırılır ve nedeni yazılır; keşif örneklemi trend skoruna girmez (test).
- **Erişim:** `verified` site; `pro`/`team` · **kaynak proje:** `seo-drift history` benzeri `[K]`

### Grup F: İzleme ve drift

#### F-50 Zamanlı izleme
- **Hikâye:** Sitemi haftalık/günlük otomatik denetleyip bozulmaları öğreneyim.
- **Tasarım:** belge 02 §12, belge 05 §9.4.
- **Faz:** 3 · **Bağımlılık:** F-60 (doğrulama), F-06
- **Kabul:** yalnız doğrulanmış sitelerde; çekirdek (sabit) + keşif (dönen tohum) örneklemi; plan sınırlarını aşan zamanlama reddedilir; hedef host nezaket sınırları aynen geçerli.
- **Erişim:** `verified` + `pro`/`team` · **kaynak proje:** yok (manuel `/seo drift`) `[K]`

#### F-51 Drift olayları (değişim uyarıları)
- **Hikâye:** `noindex` eklenmesi, canonical değişmesi, başlığın silinmesi gibi regresyonlardan haberdar olayım.
- **Tasarım:** belge 01 §10, belge 02 §12.
- **Faz:** 3 · **Bağımlılık:** F-50, baseline
- **Kabul:** 17 kural (8 Critical / 6 Warning / 3 Info) `[doğrulandı: drift_compare.py]`; kaynağın `test_drift_*.py` testleri yeşil; **skoru etkilemez**; baseline yoksa kural çalışmaz ve nedeni yazılır.
- **Erişim:** `verified` + `pro`/`team` · **kaynak proje:** `seo-drift` (`baseline|compare|history`) `[doğrulandı: skills/seo-drift/SKILL.md argument-hint]`

#### F-52 Bildirimler
- **Hikâye:** Kritik bir değişiklikte e-posta veya webhook ile uyarılayım.
- **Tasarım:** belge 06.
- **Faz:** 3 · **Bağımlılık:** F-51
- **Kabul:** yalnız eşik üstü olay için; tekilleştirme (aynı olay tekrar bildirilmez); webhook imzalı.
- **Erişim:** `pro`/`team` · **kaynak proje:** yok `[B]`

### Grup G: Doğrulama, kota ve hesap

#### F-60 Site sahipliği doğrulama
- **Hikâye:** Sitemin sahibi olduğumu kanıtlayıp daha geniş tarama ve izleme açayım.
- **Tasarım:** belge 05 D11, belge 04 (`site_verifications`).
- **Faz:** 3 (tier mantığı 2a'da kodda hazır) · **Bağımlılık:** –
- **Kabul:** DNS TXT veya `<meta>`/dosya yöntemi; sahte doğrulama denemeleri başarısız (test); doğrulama süresi ve yeniden doğrulama tanımlı; doğrulama kaldırılınca `unverified` sınırlarına dönülür.
- **Erişim:** hepsi · **kaynak proje:** yok `[B]`

#### F-61 Kota katmanları (`unverified` / `verified`)
- **Hikâye:** Sınırlarımı ve neden olduklarını göreyim.
- **Tasarım:** §2, belge 05 §10-§11, belge 02 §8.
- **Faz:** 2a (`unverified` tavanı), 3 (`verified`) · **Bağımlılık:** çok kiracılılık
- **Kabul:** bütçe `validate` aşamasında katman ve plandan **türetilir**; kullanıcı girişi bütçeyi artıramaz (test); hedef host sınırı **kiracılar arası paylaşılır**.
- **Erişim:** hepsi · **kaynak proje:** yok (prompt'taki "500 sayfa" kodsuzdu) `[doğrulandı: belge 05 §2]`

#### F-62 Hesap, API anahtarı ve kullanım görünümü
- **Hikâye:** API anahtarı üretip kullanımımı ve kalan kotamı göreyim.
- **Tasarım:** belge 06, belge 04 (`usage_ledger`).
- **Faz:** 1 (tek kiracı API anahtarı), 2a (çok kiracılı, RLS) · **Bağımlılık:** –
- **Kabul:** anahtar yalnız bir kez gösterilir, hash'li saklanır; kullanım (denetim sayısı, LLM maliyeti) `usage_ledger`'dan okunur; kiracı izolasyonu testi.
- **Erişim:** API erişimi `pro`/`team` `[?]` · **kaynak proje:** yok `[B]`

#### F-63 BYOK (kendi API anahtarını getir)
- **Hikâye:** LLM maliyetini kendi anahtarımla karşılayayım.
- **Tasarım:** belge 00 §3.4, belge 02 §9.5.
- **Faz:** 2b · **Bağımlılık:** F-62, şifreli saklama (KMS veya eşdeğeri)
- **Kabul:** **yalnız Katman C** için kullanılır (Katman A her zaman bizim); anahtar şifreli, kiracı başına; **hiçbir log, hata mesajı veya düz metin DB alanında yok** (sızıntı taraması testi); ekranda maskeli ipucu; silme ve rotasyon.
- **Erişim:** `pro`/`team` `[?]` · **kaynak proje:** kullanıcının kendi Claude aboneliği (L6) → dönüştürüldü `[doğrulandı: belge 00 §3]`

#### F-64 LLM kotası ve maliyet görünürlüğü
- **Hikâye:** Bir denetimin tahmini ve gerçekleşen LLM maliyetini göreyim.
- **Tasarım:** belge 02 §9.5, belge 00 §3.4.
- **Faz:** 2b · **Bağımlılık:** `llm_calls`, `usage_ledger`
- **Kabul:** denetim başına tavan aşılınca Katman C otomatik durur (`partial`); önbellek isabeti maliyet 0 yazılır; LLM yalnız K ≤ 5 sayfada çalışır.
- **Erişim:** plan kotasına bağlı `[?]` · **kaynak proje:** yok `[B]`

### Grup H: Google verisi

#### F-70 Google Search Console (URL Inspection ve performans)
- **Hikâye:** Google'ın sayfamı nasıl indekslediğini (indeks durumu, seçtiği canonical) göreyim.
- **Tasarım:** belge 00 §3.1 (L2), belge 09 Faz 3.
- **Faz:** 3 · **Bağımlılık:** F-60, OAuth web akışı, kiracı izolasyonu
- **Kabul:** **fail-closed property çözümü**: yanlış site eşlemesi reddedilir (test); OAuth token şifreli; varsayılan global property'ye güvenilmez `[K: google_properties]`. GA4 ve CrUX geçmişi bu özelliğe dahil değil, Faz 4+ `[?]`.
- **Erişim:** `verified` + `pro`/`team` · **kaynak proje:** `/seo google` (GSC, PageSpeed, CrUX, Indexing, GA4, PDF) `[doğrulandı: README komut listesi]`

### Grup I: Yönetim ve kötüye kullanım

#### F-80 Bot kimliği, bilgi sayfası ve engelleme
- **Hikâye (site sahibi):** Bu botun kim olduğunu öğreneyim ve gerekirse engelleyeyim.
- **Tasarım:** belge 05 §6.2, belge 02 §15.3 (D10).
- **Faz:** 1 (alfadan önce şart) · **Bağımlılık:** alan adı
- **Kabul:** `SEOAnalyzerBot/1.0 (+bilgi URL'i)` kimliği (Googlebot taklidi yok); bilgi sayfası iletişim ve IP aralığı yayınlar; `robots.txt` engeli ve başvuru yoluyla muafiyet; engel listesi `validate` aşamasında denetlenir.
- **Erişim:** herkese açık · **kaynak proje:** kaynak Chrome taklidi UA + `--googlebot` kullanır → **bilinçli olarak alınmadı** `[doğrulandı: url_safety.py:899, fetch_page.py:72]`

#### F-81 Dış istek denetim kaydı
- **Hikâye (operatör):** Bir site sahibi şikayet ettiğinde kimin, ne zaman, kaç istek yaptığını göstereyim.
- **Tasarım:** belge 02 §15.2.
- **Faz:** 1 · **Bağımlılık:** –
- **Kabul:** her dış istek için `tenant_id`, `audit_id`, hedef host, zaman, durum; günlükte sorgu parametreleri maskeli.
- **Erişim:** iç · **kaynak proje:** yok `[B]`

#### F-82 SSRF denemesi kaydı ve otomatik kısıt
- **Hikâye (operatör):** Özel ağa istek yollamaya çalışan hesaplar otomatik kısıtlansın.
- **Tasarım:** belge 02 §15.2, belge 05 §5.
- **Faz:** 2a · **Bağımlılık:** F-81
- **Kabul:** her ret ayrı kaydedilir; tekrar eden kiracıda otomatik kısıt (eşik D16, `[?]`); asla yeniden denenmez.
- **Erişim:** iç · **kaynak proje:** yok `[B]`

#### F-83 Operatör (yönetici) paneli
- **Hikâye (operatör):** Kuyruğu, kullanıcı kotalarını ve engel listesini yönetmek istiyorum.
- **Tasarım:** belge 02 §15-§16 (yalnız gözlemlenebilirlik), belge 09'da ayrı bir madde **yok**.
- **Faz:** 2c `[?]` · **Bağımlılık:** F-81, F-82
- **Kabul:** kiracı arama, kota değiştirme, engel/muafiyet ekleme, özellik bayrağı değiştirme; **her eylem denetim kaydına yazılır**; yetki ayrımı (okuma/yazma).
- **Erişim:** iç · **kaynak proje:** yok `[B]`

#### F-84 Özellik bayrakları
- **Hikâye (operatör):** Riskli bir özelliği olay sırasında kapatabileyim.
- **Tasarım:** §7.
- **Faz:** 1 · **Bağımlılık:** –
- **Kabul:** bayrak değişimi dağıtım gerektirmez; küresel ve kiracı bazlı; kapatılan özellik kullanıcıya "geçici olarak kapalı" gösterilir (hata değil).
- **Erişim:** iç · **kaynak proje:** yok `[B]`

#### F-85 Gizlilik, saklama ve silme
- **Hikâye:** Verilerimin ne kadar süre saklandığını bileyim ve silebileyim.
- **Tasarım:** belge 04 (saklama), belge 09 §8 (hukuki gözden geçirme).
- **Faz:** 2c `[?]` (genel yayın önkoşulu) · **Bağımlılık:** nesne depolama yaşam döngüsü
- **Kabul:** HTML gövdeleri varsayılan **30 gün** `[?]`, bulgular/skorlar süresiz; kiracı silme talebi tüm verisini siler (test); KVKK/GDPR değerlendirmesi tamamlanmış `[?]`.
- **Erişim:** hepsi · **kaynak proje:** yok `[B]`

### Grup J: Dil

#### F-90 Türkçe/İngilizce arayüz ve rapor; Türkçe içerik desteği
- **Hikâye:** Raporu ve arayüzü Türkçe okuyayım; Türkçe sitemdeki içerik kontrolleri doğru çalışsın.
- **Tasarım:** belge 01 §4.0, belge 00 §3.5 (L7), belge 06 (`message_key` + parametre).
- **Faz:** Arayüz/rapor TR+EN: 1 · Türkçe içerik kontrolleri: **2b** · **Bağımlılık:** Türkçe stopword/kalıp listeleri, doğrulama kümesi
- **Kabul:** bulgu mesajları kural kaydında anahtar+parametre olarak tutulur (çeviri mümkün); **Faz 1'de** `title-not-reflected-in-content` ve `description-not-reflected-in-content` Türkçe sayfada kapalı (`language-unsupported`) ve Katman B kapalı `[doğrulandı: page_checks.STOPWORDS yalnız İngilizce]`; 2b'de yanlış pozitif oranı kabul eşiğinin altındaysa açılır (eşik `[?]`).
- **Erişim:** hepsi · **kaynak proje:** İngilizce heuristikler `[K]` (Türkçe için yeniden yazılır)

---

## 4. Plan matrisi (özellik × plan / site katmanı)

Gösterim: ✅ dahil · ➖ yok · ◐ sınırlı (`[?]` sayısal sınır belirlenmedi) · 🔒 yalnız `verified` site. **Fiyat yoktur;** ◐ değerleri plan tasarımında belirlenecek.

| Özellik | free | pro | team | Not |
|---|---|---|---|---|
| F-01 Sayfa analizi | ✅ | ✅ | ✅ | |
| F-02 Site denetimi | ◐ (en çok 25 sayfa, `unverified`) | ✅ | ✅ | Tavan site katmanına bağlı |
| F-04, F-05 İlerleme, iptal | ✅ | ✅ | ✅ | |
| F-06 Örneklem/kapsam raporu | ✅ | ✅ | ✅ | Kullanıcı tanımlı URL sayısı ◐ |
| F-07 Render / `js_gap` | ➖ `[?]` | ✅ | ✅ | Maliyet ve güvenlik yüzeyi |
| F-10..F-14, F-16 Skor, kapı, kapsam, güven, ölçülmedi, sürüm | ✅ | ✅ | ✅ | Çekirdek değer, kısıtlanmaz |
| F-15 Danışma skoru | ◐ / ➖ `[?]` | ✅ | ✅ | LLM maliyeti |
| F-17 Performans (PSI/CrUX) | ◐ | ✅ | ✅ | PSI kotası bizde |
| F-18 AI arama hazırlığı | ✅ (deterministik) | ✅ + yorum | ✅ + yorum | |
| F-20 Bulgu listesi, F-24 Schema doğrulama | ✅ | ✅ | ✅ | |
| F-21 4 fazlı aksiyon planı | ◐ (öncelik listesi) | ✅ | ✅ | |
| F-22 Öne çıkanlar / hızlı kazanımlar | ✅ | ✅ | ✅ | |
| F-23 Yanlış pozitif bildirimi | ✅ | ✅ | ✅ | |
| F-25 Schema üretimi | ➖ `[?]` | ✅ | ✅ | |
| F-30 HTML rapor | ✅ | ✅ | ✅ | TR/EN |
| F-31 JSON dışa aktarma | ◐ | ✅ | ✅ | |
| F-32 PDF | ➖ | ✅ | ✅ | |
| F-33 Paylaşılabilir bağlantı | ➖ `[?]` | ✅ | ✅ | |
| F-40 Soru-cevap | ◐ / ➖ `[?]` | ✅ (kotalı) | ✅ (kotalı) | |
| F-41 Modül yeniden çalıştırma | ◐ (yalnız Katman A/B) | ✅ | ✅ | Katman C kotadan düşer |
| F-42 Geçmiş | ◐ (saklama kısa) | ✅ | ✅ | |
| F-43 Trend | ➖ | 🔒 ✅ | 🔒 ✅ | |
| F-50..F-52 İzleme, drift, bildirim | ➖ | 🔒 ✅ | 🔒 ✅ | Yalnız doğrulanmış site |
| F-60 Doğrulama | ✅ | ✅ | ✅ | |
| F-62 API anahtarı | ➖ | ✅ | ✅ | |
| F-63 BYOK | ➖ `[?]` | ✅ | ✅ | |
| F-64 LLM kotası görünürlüğü | ◐ | ✅ | ✅ | |
| F-70 GSC | ➖ | 🔒 ✅ | 🔒 ✅ | |
| F-83 Operatör paneli | iç | iç | iç | Kullanıcıya açık değil |

**Site katmanı sınırları** (`unverified` / `verified`) belge 05 D11'e göredir: 25 / 50-200 sayfa; `unverified` düşük hız ve günlük kota, `verified` daha yüksek hız.

## 5. Faz × özellik matrisi

| Faz | Özellikler |
|---|---|
| **0** | (özellik yok) `safefetch`, hostile testler, şema, kural kaydı iskeleti, prototipler P1-P4 |
| **1** | F-01, F-03, F-04, F-05, F-10, F-11, F-12, F-13, F-14, F-16, F-20, F-21 (öncelik listesi), F-22 (basit), F-23, F-24, F-30, F-31, F-62 (tek kiracı), F-80, F-81, F-84, F-90 (arayüz TR/EN) |
| **2a** | F-02, F-06, F-07, F-17, F-18 (deterministik), F-42, F-61 (`unverified`), F-62 (çok kiracılı), F-82 |
| **2b** | F-15, F-18 (yorum), F-21 (4 fazlı plan), F-22 (tam), F-33 `[?]`, F-40, F-41, F-63, F-64, F-90 (Türkçe içerik) |
| **2c** | F-25, F-83 `[?]`, F-85 `[?]` · **genel yayın (beta) önkoşulları:** D16, bot sayfası, egress dağıtım testi, kalibrasyon v1, hukuki gözden geçirme |
| **3** | F-32, F-43, F-50, F-51, F-52, F-60, F-61 (`verified`), F-70 |
| **4+** | GA4/CrUX geçmişi, hreflang tam denetim, görsel/ekran görüntüsü, agentic tam, backlink, yerel/harita, e-ticaret, SXO/cluster/content-brief/competitor-pages/programmatic/plan/flow, ücretli veri extension'ları (belge 00 §2.3, belge 09 §10) |

**Not:** F-33, F-83, F-85 belge 09'da açıkça yer almayan ama genel yayın için gerekli görülen özelliklerdir; faz atamaları `[?]` ve belge 09'a işlenmelidir (§9).

## 6. Yapılmayacaklar (non-features)

| # | Özellik | Neden | Hafifletme / yönlendirme |
|---|---|---|---|
| N-1 | **Yerel / staging / özel ağ denetimi** | SSRF yüzeyi; kullanıcı kararı: yalnız internetteki canlı sunucular (belge 00 §3.1, L1) | Planlanmıyor; HTML yükleme ve self-hosted sürüm de kapsam dışı |
| N-2 | **Googlebot kimliğiyle fetch** | Üçüncü tarafın kimliğini taklit etmek; Google IP doğrulayan WAF'larda yanlış sonuç (L2) | `js_gap`; sahipler için GSC (F-70) |
| N-3 | **Serbest biçimli LLM komutları** | Ürün sabit, test edilebilir akıştır (L3) | F-40 Q&A ve F-41 yeniden çalıştırma |
| N-4 | **Genel skorda LLM yargısı** | Tekrarlanabilirlik (L4); kullanıcı kararı: ek telafi yapılmaz | F-15 danışma skoru (skor dışı) |
| N-5 | **"500 sayfa" tam site taraması** | Kodla doğrulanmamış prompt metniydi (L5); maliyet ve nezaket | Örneklem + kapsam raporu, dönen keşif örneklemi (F-06) |
| N-6 | **Kullanıcının kendi Claude aboneliğiyle çalışma** | Ürün olarak LLM maliyeti bizde (L6) | Önbellek, sınırlı Katman C, BYOK (F-63) |
| N-7 | **Türkçe'de Katman B (şimdilik)** | Kalıp listeleri İngilizce (L7) | Faz 2b'de Türkçe listeler (F-90) |
| N-8 | **SERP sıralama tahmini / "sıralama garantisi" dili** | Kaynak da skorların Google'ın iç sinyalleri olmadığını söyler (heuristik); yanıltıcı iddia riski | Rapor dili: "ölçüt/öneri", asla "şu kadar sıralama kazanırsınız" |
| N-9 | **Google SERP kazıma** | Kullanım şartları, kırılganlık | Ücretli SERP veri sağlayıcıları ancak Faz 4+ ve ayrı karar |
| N-10 | **İçerik/görsel üretim araçları** (content-brief, image-gen, competitor-pages, programmatic) | Strateji/üretim odaklı, SERP verisi gerekir, çekirdek değer değil | Faz 4+ (belge 00 §2.3) |
| N-11 | **Faturalama/ödeme, SSO/kimlik sağlayıcı** | Kapsam dışı (belge 09 §13) | Plan sınırları kodda; ödeme sonra |
| N-12 | **Ayrı SPA arayüzü, mobil uygulama, beyaz etiket, çok bölgeli dağıtım** | Kapsam dışı (belge 09 §13) | Sunucu tarafı HTML ile başlanır; TypeScript arayüz belge 06 kararına bağlı |
| N-13 | **Ham HTML'i LLM'e vermek** | Prompt injection (belge 02 §9.3) | Yalnız çıkarılmış alanlar |
| N-14 | **Aynı rapor üzerinde skoru sessizce yeniden hesaplamak** | Raporlar değiştirilemez; sürüm sözleşmesi | Yeniden hesap = yeni denetim satırı (belge 02 §11.2) |

## 7. Özellik bayrakları

Bayraklar **küresel** ve **kiracı bazlı** değiştirilebilir (F-84). Varsayılanlar canlı ortam içindir.

| Bayrak | Kapsadığı özellik | Varsayılan | Kill-switch? | Neden riskli |
|---|---|---|---|---|
| `ff.site_mode` | F-02 | açık (Faz 2a'dan sonra) | **evet** | Hedef host yükü, maliyet |
| `ff.render` | F-07 | açık, `free`'de kapalı `[?]` | **evet, birincil** | Chromium TOCTOU, bellek, maliyet (belge 05 §5.3); P3 başarısızsa kapalı kalır |
| `ff.exploration_sample` | F-06 keşif örneklemi | açık | evet | Yük, trend karışması |
| `ff.layer_b` | Katman B heuristikleri (dil bazında) | İngilizce açık, Türkçe kapalı | evet | Yanlış pozitif |
| `ff.lang_tr_checks` | Dile bağlı 2 kontrol + Katman B Türkçe | kapalı (Faz 2b'ye kadar) | evet | Yanlış pozitif |
| `ff.llm_layer_c` | F-15, F-18 yorumu, F-21 metni | açık (Faz 2b'den sonra) | **evet, birincil** | Maliyet, tutarsızlık, injection |
| `ff.qa` | F-40 | açık (Faz 2b'den sonra) | **evet** | Maliyet, injection, kapsam dışı sohbet |
| `ff.byok` | F-63 | açık (Faz 2b'den sonra) | **evet** | Gizli anahtar sızıntı riski |
| `ff.psi` | F-17 | açık | evet | Kota/maliyet |
| `ff.schema_generate` | F-25 | açık (2c'den sonra) | evet | Yanlış/geçersiz kod önerisi |
| `ff.pdf` | F-32 | açık (Faz 3) | evet | Bağımlılık, kaynak kullanımı |
| `ff.monitoring` | F-50..F-52 | açık (Faz 3) | evet | Sürekli yük |
| `ff.gsc` | F-70 | açık (Faz 3) | evet | Kiracı izolasyonu |
| `ff.public_signup` | Yeni kiracı kaydı | kapalı (alfa), beta'da açık | **evet** | Kötüye kullanım |
| `ff.share_links` | F-33 | `[?]` | evet | Veri sızıntısı |

**Kural:** kill-switch'in etkisi **hata değil, görünür bir "geçici olarak kapalı" durumudur**; çalışan denetimler kapatılan modülü `skipped` (neden kodu `feature-disabled`) olarak geçer ve kapsam buna göre düşer, denetim `partial` olabilir.

## 8. Ürün metrikleri ve başarı ölçütleri

Hedeflerin çoğu **önceki belgelerden alınmıştır**; yeni sayılar `[?]` ile işaretlidir ve Faz 1-2a ölçümüne göre güncellenir.

| Alan | Metrik | Hedef | Kaynak/Not |
|---|---|---|---|
| **Doğruluk** | Kural başına yanlış pozitif oranı (kullanıcı bildirimi + alfa incelemesi) | Eşik `[?]` (Faz 1 verisinden); Türkçe için açılış kriteri | Belge 09 §7.2, F-23 |
| | Skor-uzman uyumu (Spearman) | ≥ 0.7 | Belge 01 §13.2, Faz 2a çıkışı |
| | Kaynak parity testleri (id+severity) | %100 aynı (belgelenmiş farklar hariç) | Belge 00 §4 |
| **Tekrarlanabilirlik** | Aynı girdi → aynı skor | %100 (özellik testi); örneklem aynı tohumla aynı | Belge 01 P1, belge 05 §9.4 |
| **Kapsam** | `pages_fetched / pages_planned` | ≥ %90 `[?]`; `< 30` sayfada güven ≤ orta | Belge 05 §9.4, belge 01 §8.5 |
| | "Yetersiz veri" (kapsam < 60) oranı | İzlenir, hedef `[?]` | F-12 |
| **Hız (p95)** | Sayfa analizi LLM'siz / LLM'li | < 20 sn / < 60 sn | Belge 02 §14 (D15, ölçülecek) |
| | Site denetimi 50 sayfa LLM'siz / LLM'li | < 3 dk / < 5 dk | Belge 02 §14 |
| **Güvenilirlik** | Tamamlanan/kısmi/başarısız denetim oranı | `failed` yalnız `target-rejected`/`unreachable`; kod kaynaklı `failed` ≈ 0 | Belge 02 §4.1 |
| | Kural istisnası sayısı | Alarm eşiği `[?]` | Belge 02 §6, §15.1 |
| **Maliyet** | Ortalama LLM maliyeti/denetim | Plan sınırı altında `[?]` | F-64 |
| | Önbellek isabet oranı | İzlenir, hedef `[?]` | Belge 02 §9.4 |
| | PSI çağrısı/denetim | Kota altında | F-17 |
| **Nezaket** | Hedef host'un gördüğü istek hızı | Sınırın altında (yük testi), şikayet sayısı ≈ 0 | Belge 05 §10 |
| | Devre kesici tetiklenme oranı | İzlenir | Belge 02 §8.1 |
| **Güvenlik** | SSRF reddi denemesi sayısı, otomatik kısıtlanan kiracı | İzlenir | F-82 |
| | BYOK sızıntı taraması | 0 bulgu | F-63 |
| **Kullanıcı** | Bulgu başına "yararlı/yanlış" geri bildirimi | İzlenir | F-23 |
| | Denetimden sonra yeniden çalıştırma / trend takibi | Düzeltme döngüsü göstergesi (`[?]`) | F-41, F-43 |

**Anlamlı başarı tanımı:** kullanıcı raporu açıp bir bulguyu düzeltir, modülü yeniden çalıştırır ve skorun iyileştiğini görür. Skorun mutlak değeri hedef değildir; **kalibrasyonlu, tekrarlanabilir ve açıklanabilir** olması hedeftir.

## 9. Doğrulama matrisi (kaynak projeye dayanan iddialar)

| İddia | Kontrol | Sonuç |
|---|---|---|
| 26 sub-skill ve 19 ajan | `ls skills` = 26, `ls agents` = 19; README "26 sub-skills and 19 specialist agents" | ✅ |
| Komut listesi: 30 çekirdek+extension komut | README satır 116 | ✅ |
| `/seo audit`, `/seo page`, `/seo schema`, `/seo google`, `/seo drift` komutları | README komut grupları | ✅ |
| `/seo schema`: algıla, doğrula, üret | README "Schema and AI Search" | ✅ |
| `seo-drift`: `baseline\|compare\|history <url>` | `skills/seo-drift/SKILL.md` `argument-hint` | ✅ |
| `seo-audit` PDF raporu `google_report.py --type full` ile üretir ve her denetimden sonra sunar | `skills/seo-audit/SKILL.md` satır 60 | ✅ |
| Page Score Card 5 kategori (Sayfa içi, İçerik, Teknik, Schema, Görseller) | `skills/seo-page/SKILL.md` "Output" (bu oturumda okundu) | ✅ |
| 47 `page_checks` kontrolü, severity dağılımı 2/6/24/15 | `page_checks.py` AST sayımı (belge 01 §12) | ✅ |
| Drift 17 kural, 8/6/3 | `drift_compare.py` (belge 01 §12) | ✅ |
| Health Score'u hiçbir script hesaplamıyor | `scripts/` ve `tests/` araması (belge 01 §12) | ✅ |
| Crawl kuyruğu, `can_fetch`, 429/retry kodu yok | Belge 05 §14 | ✅ |
| CWV eşikleri | `pagespeed_check.CWV_THRESHOLDS` | ✅ |
| Kaynak Chrome taklidi UA ve `--googlebot` kullanır | `url_safety.py:899`, `fetch_page.py:72,377` | ✅ |
| `STOPWORDS` yalnız İngilizce | `page_checks.py:236` | ✅ |
| Rapor severity'lerinin hepsi aynı amber | Belge 08 bulgusu (`google_report.py`) | ✅ (bu belgede yeniden okunmadı) |
| E-E-A-T ağırlıkları "Google'ın değil" notu | `agents/seo-content.md` (belge 02 §18) | ✅ |
| Q&A, kota katmanları, BYOK, plan, izleme zamanlayıcısı, özellik bayrakları kaynakta **yok** | Skill kataloğu (belge `kaynak analizi notları 04`) ve README'de eşleniği görülmedi; **kapsamlı kod araması yapılmadı** | ◐ "kaynakta eşleniği bulunamadı" düzeyinde |
| `schema_generate.py` hangi tipleri üretir | Dosya varlığı doğrulandı; skill kataloğu SKILL.md'lerde adıyla anılmadığını not ediyor | **Doğrulanmadı** (taşıma sırasında kontrol edilecek) |
| `google_properties` fail-closed çözümü | Varlık doğrulandı (belge 05 raporu); satır satır okunmadı | ◐ |

**Doğrulanmadı / bu belgede ele alınmayan:** kesin plan sınırları (denetim sayısı, LLM kotası, saklama süresi), `free` planında hangi LLM özelliklerinin açık olacağı, GA4/CrUX geçmişi kapsamı, paylaşılabilir bağlantı ve operatör panelinin faz ataması.

## 10. Açık kararlar

| # | Karar | Öneri | Not |
|---|---|---|---|
| FT1 | **Plan yapısı**: `free`/`pro`/`team` adları, sayısal sınırlar (denetim/ay, LLM kotası, saklama süresi) | Adlar geçici; sınırlar Faz 2a kalibrasyon ve maliyet ölçümünden sonra | Belge 04'te `plan` enum'u geçici |
| FT2 | **`free` planında LLM (Katman C, Q&A, danışma skoru)** açık mı? | Küçük kotalı veya kapalı; Katman A/B her zaman açık (çekirdek değer) | Maliyet sürdürülebilirliği |
| FT3 | **Render `free`'de açık mı?** | Kapalı (maliyet + güvenlik yüzeyi) | `ff.render` |
| FT4 | **Paylaşılabilir rapor bağlantısı (F-33)**: kapsam, süre, gizlilik | Faz 2b, imzalı ve süreli, `noindex` | Belge 09'a eklenmeli |
| FT5 | **Operatör paneli (F-83)** ve **gizlilik/silme (F-85)**: faz ataması | Faz 2c, genel yayın önkoşulu | Belge 09 §8 önkoşul listesine eklenmeli |
| FT6 | **`unverified` varsayılan örneklem**: belge 05 D7 "varsayılan 50" derken D11 "doğrulanmamış 25" der | `unverified` 25, `verified` varsayılan 50 / üst sınır 200 (§2) | Belge 05 §9.4 ve belge 09 Faz 2a metni hizalanmalı |
| FT7 | **Bulgu geri bildirimi (F-23)** süreci: kim inceler, kurallara nasıl yansır | Alfada manuel inceleme; kural bazında sayaç | Doğruluk metriğinin girdisi |
| FT8 | **GA4 ve CrUX geçmişi** hangi fazda | Faz 4+; GSC (F-70) ile birlikte değerlendirilir | |
| D2, D4, D6, D7, D8, D10, D11, D12, D13, D14, D15, D16 | (belge 01, 02, 05'ten) | Önerilerle ilerlenir, onay bekler | Belge 10 karar günlüğünde izlenir |

## 11. Sonraki belgeler

| Belge | Konu | Bu belgeden devraldığı |
|---|---|---|
| `08-file-structure.md` | Depo ve paket yapısı | Özellik → modül eşlemesi (F-xx → `src/seoa/...`) |
| `09-implementation-roadmap.md` | Faz faz uygulama | §5 faz × özellik matrisi; F-33/F-83/F-85 ve FT6 hizalaması |
| `10-decision-log.md` | Karar günlüğü | FT1-FT8 ve önceki açık kararlar |
| `06-io-schemas.md` | API ve `audit.json` | F-04, F-31, F-33, F-40, F-41, F-62 uç noktaları ve şemaları |
| `04-data-model.md` | Tablolar | `plan`, `tier`, `usage_ledger`, `qa_*`, `byok_keys`, `monitoring_schedules`, bayrak depolama |
