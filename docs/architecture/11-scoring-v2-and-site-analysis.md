# 11. Skor v2 ve Derin Site Analizi

> Durum: **Taslak v0.1** · Tetikleyen gözlem: iki gerçek denetimde (aramada hiç çıkmayan bir site 96.4; çok sayıda görselli bir site 91.9) skorun **neyi ölçmediği** kullanıcıya belli değildi.
> Referans: kaynak proje `skills/seo-technical/SKILL.md` ("Each category score is the share of that category's checks that passed, adjusted for severity; a category you could not measure is reported as 'not measured'; show the checks behind every score"), `skills/seo-images/SKILL.md` (boyut eşikleri), `skills/seo-page/SKILL.md`, `skills/seo-content/SKILL.md` `[doğrulandı]`.

## 1. Sorun

| Gözlem | Neden |
|---|---|
| Skor yüksek ama site aramada çıkmıyor | Skor yalnız **teknik ve sayfa içi hijyen** ölçüyor; indeksleme, sıralama, geri bağlantı, site yaşı ölçülmüyor ve rapor bunu söylemiyor |
| Çok görselli sitede skor yine yüksek | Eski formül yalnızca **ceza çıkarıyordu** (geçen kontroller görünmüyordu); görsel kategorisi %5 ağırlıkta ve Orta şiddet tavanı 30 puan |
| Boyut, hız, bağlantılar ölçülmüyor | Yalnız HTML ayrıştırılıyordu; sayfa ağırlığı, kaynaklar, LCP/CLS, bağlantı sağlığı yoktu |

## 2. Skor v2 (`score_version = mvp-0.2`)

### 2.1 Kategori skoru: geçen kontrollerin şiddetle ağırlıklı payı

```
w(k)        = {Critical: 8, High: 4, Medium: 2, Low: 1, Info: 0}[kural şiddeti]
s(k)        = 1 − (kuralın başarısız olduğu sayfa / değerlendirilen sayfa)      sayfa kapsamlı kural
            = 0 (bulgu var) veya 1 (yok)                                          site kapsamlı kural
skor(c)     = 100 × Σ w(k)·s(k) / Σ w(k)       (kategorideki UYGULANABİLİR kurallar)
```

- **Geçen kontroller de sayılır** (payda): 40 kontrolden 2'si kalıyorsa bu görünür ("38/40 geçti"), eski "yalnız ceza" modelinde görünmezdi.
- **Uygulanabilirlik:** kuralın kategorisi, modu (`modes`), gereken veri (`requires`: `lab`, `psi`, `rendered`) ve `not_checked` durumu elenir. Ölçülemeyen kural paydadan çıkar, **geçti sayılmaz** (belge 01 P2).
- Her kategori için **kontrol tablosu** döner (`checks[]`: id, şiddet, ağırlık, geçme oranı, etkilenen/değerlendirilen sayfa) ve `penalties[]` = her başarısız kuralın **kaybettirdiği puan** (`100·w·(1−s)/Σw`).
- Kapı (gate), kapsam %, güven, çekirdek örneklem skoru, P25: belge 01 §8 ile aynı.

### 2.2 Kategoriler ve ağırlıklar

kaynak proje (22/23/20/10/10/10/5) başlangıç alındı; **Bağlantılar** eklendi (kaynak proje bunu On-Page/Technical altında dağınık tutar: "no orphan pages", "important pages within 3 clicks"), Performans ve Görseller artık **doğrudan ölçüldüğü** için ağırlıkları artırıldı.

| Kategori | v0.1 | **v0.2** | Ne ölçer |
|---|---|---|---|
| Teknik | 25 | **20** | tarama, indeksleme, güvenlik başlıkları, TLS, sitemap, robots, mobil |
| İçerik | 20 | **20** | kelime, tekrar (kopya içerik), bağlama göre ince içerik |
| Sayfa içi | 20 | **15** | title/description/H1/URL/OG |
| **Bağlantılar (yeni)** | – | **10** | kırık, yönlenen, yetim sayfa, tıklama derinliği, çapa metni, dış bağlantı sağlığı |
| Performans | 10 | **12** | LCP/CLS/FCP (lab), sayfa ağırlığı, istek sayısı, sıkıştırma, önbellek, üçüncü taraf |
| Schema | 10 | **8** | JSON-LD doğrulama |
| AI arama | 10 | **8** | AI tarayıcı erişimi, JS bağımlılığı, llms.txt |
| Görseller | 5 | **7** | boyut (KB), format, gerçek boyuta göre büyük, alt, lazy |
| **Toplam** | 100 | **100** | |

Ağırlıklar bu ürünün **iç modelidir**; Google sayısal ağırlık yayınlamaz. Kalibrasyon yapılana kadar "tahmini model" etiketi taşır.

### 2.3 Skorun adı ve sınırı
"SEO Sağlık Skoru" → **"Teknik ve Sayfa İçi Sağlık Skoru"**. Raporun başında **"Bu skor neyi ölçmez"** kutusu: indeksleme durumu, aramadaki sıralama, geri bağlantılar ve otorite, anahtar kelime/niyet uyumu, saha (gerçek kullanıcı) hız verisi, rakip karşılaştırması.

## 3. Yeni analizler

### 3.1 Bağlantı analizi (`analysis/links.py`)
Örneklenen sayfaların bağlantılarından bir **bağlantı grafiği**: her bağlantı için kaynak, hedef, çapa metni, `rel`, bölge (nav/footer/main), hedef durum kodu, yönlendirme sayısı. İç hedefler örneklemde varsa oradan, yoksa nazik `HEAD/GET` ile; dış bağlantılar sınırlı sayıda (varsayılan 40) ve hedef-başına hız sınırıyla kontrol edilir. Çıktı: özet (iç/dış/benzersiz, dış alan adları, kırık, yönlenen, nofollow), sayfa başına giden/gelen bağlantı ve **tıklama derinliği** (ana sayfadan), **yetim sayfalar** (sitemap'te var, örneklemde hiçbir sayfadan bağlanmamış).
Bulgular: `broken-internal-link`, `broken-external-link`, `internal-redirect-link`, `orphan-page`, `deep-page` (>3 tık, kaynak proje `seo-technical`), `too-many-links`, `no-internal-links`, `generic-anchor-text` (mevcut).

### 3.2 Lab performans, boyut ve kaynaklar (`render/perf.py`, `analysis/perf_checks.py`)
Playwright ile sayfa yüklenirken: TTFB, FCP, **LCP**, **CLS**, TBT vekili (long task), DOMContentLoaded, load; tüm istekler (adet, aktarılan bayt, türe göre: belge/script/stil/görsel/font/medya), **üçüncü taraf** alan adları, render-engelleyen kaynak, **sıkıştırılmamış metin kaynakları**, önbellek başlıkları olmayan statik varlıklar. **Mobil** geçişte: yatay kaydırma, küçük yazı, küçük dokunma hedefi (24 px WCAG AA, 48 px rahat, kaynak proje). **Lab** değerdir (bu makine ve ağdan); saha verisi (CrUX/PSI) değildir ve öyle etiketlenir. CWV eşikleri: LCP ≤2.5 s, CLS ≤0.1 (INP saha verisidir, lab'da ölçülmez).
Bulgular: `cwv-lcp-*`, `cwv-cls-*` (mevcut, kaynak `lab`), `page-weight-heavy`, `too-many-requests`, `uncompressed-text-resources`, `static-assets-no-cache`, `render-blocking-resources`, `third-party-heavy`, `mobile-horizontal-scroll`, `mobile-tap-targets-small`, `mobile-font-too-small`.

### 3.3 Görsel analizi (`render/perf.py` içinde, `images` kategorisi)
Her görsel: aktarılan bayt, **sunulan format** (magic byte/Content-Type), doğal ve gösterilen boyut, `alt`, `lazy`, ekran üstü mü. kaynak proje eşikleri: küçük resim <50 KB (uyarı >100, kritik >200), içerik <100 KB (>200, >500), hero <200 KB (>300, >700). Bulgular: `image-too-large`, `image-oversized-for-display` (doğal >2× gösterilen), `image-legacy-format` (büyük JPEG/PNG; zaten WebP/AVIF sunuyorsa önerilmez), `image-above-fold-lazy` (mevcut), `images-missing-dimensions` (mevcut).

### 3.4 İndekslenebilirlik tablosu (`analysis/indexability.py`)
Sayfa başına: durum, **indekslenebilir mi** ve nedenleri (noindex, canonical başka yere, robots engeli, 4xx/5xx), canonical, sitemap'te mi, gelen bağlantı sayısı, derinlik. "Neden aramada çıkmıyor?" sorusunun **ölçülebilir** kısmını gösterir (engel yok mu?); indeksleme **durumunu** ölçmez (bkz. §3.6).

### 3.5 Kopya içerik (`analysis/duplicates.py`)
Örneklenen sayfaların ana metninde 5-kelimelik shingle Jaccard benzerliği; ≥0.85 → `duplicate-content` (kaynak proje `seo-technical`: "near-duplicates, parameter URLs, www vs non-www").

### 3.6 Görünürlük sinyalleri (skora girmez, `integrations/` + `analysis/visibility.py`)
Anahtarsız, kamuya açık kaynaklardan **bilgi amaçlı** göstergeler; sıralama tahmini değildir:
| Sinyal | Kaynak | Ne anlatır |
|---|---|---|
| Alan adı yaşı, kayıt tarihi | RDAP (`rdap.org` yönlendirmesi) | Yeni alan adı → sıralamada zaman gerekir |
| İlk/son arşiv kaydı, kayıt sayısı | Wayback CDX API | Sitenin ne kadar süredir var olduğu/taranabildiği |
| Common Crawl'da var mı, kaç sayfa | Common Crawl index API | Büyük bir web taramasının siteyi bilip bilmediği (indeksleme **vekili**, Google değil) |
| Search Console | – | **Bağlı değil** (yol haritası: Google hesabı yetkilendirmesi gerekir) |
Google'ın indeksini **sorgulamıyoruz** (arama sonucu kazımak şartlara aykırıdır); doğru yol Search Console'dur.

## 4. Mimari değişiklikler
- `Category.LINKS` ve `Stage.ANALYZE` eklenir; analiz modülleri `analyze` aşamasında (ölçümden sonra) çalışır, lab performans `render` aşamasında.
- `CheckDef` yeni alanı: `modes` (sayfa/site) ve `requires` anahtarları `lab|psi|rendered`.
- Yeni veri (bağlantılar, performans, indekslenebilirlik, görünürlük) `audit_data` tablosunda **JSON blob** olarak saklanır (`links`, `perf`, `indexability`, `visibility`); rapor bunlardan beslenir.
- Rapor: yeni bölümler (Bağlantılar, Performans ve ağırlık, Görseller, İndekslenebilirlik, Görünürlük sinyalleri), her kategoride "N/M kontrol geçti" ve kontrol tablosu.

## 5. Sınırlar (dürüst)
Lab performans bu makineden ölçülür, kullanıcıların deneyimi değildir. Dış bağlantı kontrolü örneklemlidir. Görünürlük sinyalleri indeksleme kanıtı değildir. Ağırlıklar kalibre değildir. Search Console, backlink verisi ve anahtar kelime/sıralama **yoktur**; bunlar için hesap yetkilendirmesi veya ücretli anahtar gerekir.
