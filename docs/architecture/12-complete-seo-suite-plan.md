# 12. Tam SEO Paketi: Eksik Envanteri ve Aşamalı Plan

> Durum: **Canlı belge v0.1** · Hedef: kullanıcı **tek bir arama (URL)** ile bir site hakkında öğrenilebilecek her şeyi görsün: sayfa performansı, hız, SEO ayarları, sıralama, bağlantılar, rakipler, teknoloji, görünürlük.
> Referans: kaynak projenin 26 skill'i ve extension'ları (`kaynak/skills/`, `extensions/`) `[doğrulandı: SKILL.md açıklamaları okundu]` + "olması gereken ama kaynak projede da olmayan" bir SEO paketi için bizim ekler.

## 1. Gerçekçi sınır: veri nereden gelir?

Her özellik üç kaynaktan birine dayanır. Plan buna göre sıralanır.

| Etiket | Anlamı | Örnek |
|---|---|---|
| 🟢 **Anahtarsız** | Siteyi kendimiz tararız veya herkese açık kaynaklar; hemen yapılabilir | HTML/başlık/hız/bağlantı analizi, teknoloji tespiti, önizlemeler |
| 🟡 **Ücretsiz anahtar / hesap** | Ücretsiz ama bir kez kurulum gerekir | CrUX/PageSpeed (Google API anahtarı), Search Console (OAuth), OpenPageRank |
| 🔴 **Ücretli veri** | Veriyi bir sağlayıcı satar; ücretsiz karşılığı yok | **Google sıralama (SERP) verisi, anahtar kelime hacmi, rakip trafiği, kapsamlı backlink verisi** |

**Sıralama hakkında dürüst not:** Google arama sonuçlarını kazımak Google'ın şartlarına aykırıdır ve kırılgandır. Bir sitenin "hangi kelimede kaçıncı sırada" olduğunu öğrenmenin dürüst yolları: (1) **Search Console** (kendi siteniz, ücretsiz, gerçek veri), (2) **SERP API sağlayıcısı** (DataForSEO gibi, ücretli, kaynak proje extension'ı olarak var). Başkasının sitesinin sıralamasını ücretsiz öğrenmenin güvenilir yolu yoktur. Bu yüzden kelime/sıralama özellikleri 🟡/🔴 olarak planlandı ve **anahtar verilince çalışacak şekilde** kodlanır.

## 2. Envanter: kaynak proje yetenekleri ve durumumuz

| kaynak proje skill | Bizde | Boşluk |
|---|---|---|
| seo-audit, seo-page, seo-technical | ✅ | tamamlayıcı: yönlendirme matrisi, soft-404, güvenlik dosyaları, HTTP sürümü (**A2**) |
| seo-content (E-E-A-T, okunabilirlik, ince içerik) | ◐ E-E-A-T ✅ | okunabilirlik, anahtar kelime kullanımı, terim analizi (**A5**) |
| seo-schema (algıla/doğrula/**üret**) | ◐ doğrulama ✅ | **JSON-LD önerisi üretimi**, zengin sonuç uygunluğu (**A7**) |
| seo-sitemap | ◐ analiz ✅ | sitemap **üretimi** (**C**) |
| seo-images | ✅ | — |
| seo-geo (AI görünürlüğü) | ◐ | llms.txt içerik doğrulama, Markdown erişimi, Content-Signal (**A8**) |
| seo-agentic | ✗ | ajan hazırlığı (**A8**) |
| seo-hreflang | ◐ 1 kontrol | tam hreflang denetimi: karşılıklılık, kodlar, x-default (**A6**) |
| seo-google (GSC, CrUX, GA4, Indexing) | ◐ GSC, CrUX yapılıyor | GA4 (**B3**) |
| seo-drift (izleme) | ✗ | iki denetim karşılaştırma, geçmiş, zamanlanmış tekrar (**C1**) |
| seo-backlinks | ✗ | alan adı otoritesi (OpenPageRank), kaynak çeşitliliği (**B2**) |
| seo-dataforseo (SERP, anahtar kelime) | ✗ | **kapsam dışı (kullanıcı kararı: ücretli araç yok)**; sıralama yalnız Search Console ile (**B1**) |
| seo-cluster, seo-sxo | ✗ | SERP verisi gerektirir (**B1** sonrası) 🔴 |
| seo-competitor-pages, seo-content-brief | ✗ | LLM + SERP (**C3**) |
| seo-local, seo-maps | ✗ | NAP/LocalBusiness doğrulama 🟢 (**C4**); GBP/harita 🔴 |
| seo-ecommerce | ✗ | Product schema/merchant kuralları 🟢 (**A7**); pazar verisi 🔴 |
| seo-plan, seo-programmatic, seo-flow | ✗ | strateji çıktısı, ölçekli sayfa analizi (**C5**) |
| seo-image-gen | ✗ | analiz değil üretim; kapsam dışı |
| Extension'lar (Ahrefs, SE Ranking, Profound, Bing, Matomo, Unlighthouse) | ✗ | ihtiyaç doğarsa, ücretli |

### kaynak projede da olmayan ama bir SEO paketinde olması gerekenler
Teknoloji (CMS/çerçeve/CDN/analitik) tespiti, SERP ve sosyal paylaşım **önizlemesi**, ekran görüntüleri (masaüstü/mobil, ekran üstü analizi), erişilebilirlik temelleri, kopya/near-duplicate başlık analizi (var), hedef anahtar kelime denetimi, geçmiş ve trend, rakip karşılaştırma.

## 3. Aşamalar

Her aşama kendi içinde çalışır ve bitince raporda görünür. Sıra: **en çok değer / en az bağımlılık**.

### Aşama A: Anahtarsız derin analiz 🟢 (şimdi)
| # | Modül | İçerik |
|---|---|---|
| **A1** | Teknoloji tespiti | CMS, çerçeve, barındırma/CDN, analitik, etiket yöneticisi, sunucu; başlık/meta/script/çerez imzaları |
| **A2** | Site kurulumu | yönlendirme matrisi (http/https, www/apex, sondaki eğik çizgi, büyük harf, `/index.html`), **soft-404** testi, özel 404 sayfası, HTTP sürümü ve sıkıştırma (br/gzip), HSTS preload, `security.txt`/`ads.txt`/favicon/manifest |
| **A3** | Önizlemeler | **Google SERP önizlemesi** (title/description kırpma), **sosyal kart** önizlemesi (Open Graph/Twitter, görsel boyutu/oranı doğrulama) |
| **A4** | Ekran görüntüleri | masaüstü ve mobil, ekran üstü analizi (H1/CTA görünür mü), rapora gömülü |
| **A5** | İçerik dili | okunabilirlik (İngilizce Flesch, Türkçe Ateşman), **hedef anahtar kelime denetimi** (kullanıcı girerse: title/H1/URL/açıklama/ilk 100 kelime/yoğunluk), sayfanın en sık terimleri |
| **A6** | Hreflang | geçerli kodlar, kendine referans, **karşılıklılık**, x-default, canonical çakışması |
| **A7** | Schema önerisi | sayfa tipine göre **kopyala-yapıştır JSON-LD** (Organization, WebSite, Article, Product, LocalBusiness, BreadcrumbList), zengin sonuç uygunluğu, Product/merchant kuralları |
| **A8** | Yapay zekâ/ajan hazırlığı | `llms.txt` doğrulama, Markdown erişimi, `Content-Signal`, WebMCP izi |

### Aşama B: Hesap/anahtarla zenginleştirme 🟡🔴 (kod hazır, anahtar verilince çalışır)
| # | Modül | Gereken |
|---|---|---|
| **B0** | Google: CrUX + PageSpeed + Search Console | `SEOA_GOOGLE_API_KEY`, OAuth (**yapılıyor**) |
| **B1** ✅ | **Sıralama ve anahtar kelime**: kelime listesi → alan adının konumu, ilk 10 sonuç, SERP özellikleri, kelime önerisi ve hacim, rakip keşfi | Yalnız Search Console (kendi siteniz, ücretsiz). **Ücretli sağlayıcı (DataForSEO vb.) kullanılmaz: kullanıcı kararı.** Başkasının sıralaması/kelime hacmi sunulmaz |
| **B2** | Otorite ✅ (OpenPageRank) | alan adı otorite tahmini (`integrations/openpagerank.py`, `analysis/mod_authority.py`); anahtar `SEOA_OPENPAGERANK_KEY`, yoksa 'ölçülmedi'; üçüncü taraf tahmini, skora girmez. Moz DA/PA yok |
| **B3** | GA4 organik trafik | Google OAuth (aynı akış) |

### Aşama C: Süreç ve strateji
| # | Modül | İçerik |
|---|---|---|
| **C1** | **Geçmiş ve izleme** ✅ | iki denetimi karşılaştır (yeni/çözülen bulgu, skor farkı, metrik değişimi), site başına geçmiş, elle yeniden tarama (`analysis/compare.py`, `report/history.py`; zamanlanmış tarama yok) |
| **C2** | **Rakip karşılaştırma** ✅ | kullanıcının verdiği (≤3) rakiplerin yalnız giriş sayfası, aynı hafif analizle yan yana (`analysis/mod_competitors.py`); SERP'ten rakip keşfi B1'e bağlı, yok |
| **C3** | İçerik brief'i | LLM: hedef kelime/URL için başlık yapısı, terimler, iç bağlantı önerisi |
| **C4** | Yerel SEO ✅ | NAP çıkarma (JSON-LD, tel:, metin sezgisi), farklı numara/adres tutarsızlığı, tel: bağlantısı (`analysis/mod_local.py`); `LocalBusiness` eksik alanları zaten `schema-missing-key-properties` kuralında, tekrarlanmadı |
| **C5** | Sitemap üretimi ✅ / strateji yol haritası ✗ | örneklemden önerilen `sitemap.xml` + mevcut sitemap karşılaştırması + indirme (`analysis/mod_sitemap_gen.py`); iş tipine göre yol haritası henüz yok |

### Arayüz: "tek arama, tam dosya"
Rapor şu sekmelerle düzenlenir: **Genel · Teknik · Sayfa içi · İçerik · Performans · Bağlantılar · Görseller · İndeksleme · Arama (Search Console/sıralama) · Rakipler · Teknoloji · Önizleme · Geçmiş**. Arama formuna isteğe bağlı alanlar: **hedef anahtar kelimeler**, **rakip URL'leri**, ülke/dil.

## 4. Mimari: eklenti modülleri
Her analiz bir **modül**dür (`AnalysisModule`): girdi (`AnalysisInputs`: giriş sayfası, örneklem, fetcher, renderer, ayarlar, kullanıcı seçenekleri), çıktı (`ModuleResult`: bir JSON bloğu + bulgular + ölçülemeyenler). Orkestratör kayıtlı modülleri eşzamanlı, **hata yalıtımlı** (bir modül çökerse diğerleri sürer) ve süre sınırlı çalıştırır; sonuçlar `audit_data` tablosuna tür adıyla yazılır, rapor bunları okur. Yeni modül eklemek: dosya + `register_module(...)` + rapor bölümü.

## 5. Sınırlar
Rakip trafiği, kelime hacmi ve başkasının sıralaması ücretsiz bulunamaz. Lab performans bu makineden ölçülür. Search Console yalnızca kendi (doğrulanmış) siteleriniz için çalışır. Skor ağırlıkları kalibre değildir.
