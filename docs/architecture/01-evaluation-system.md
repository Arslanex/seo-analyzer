# 01. Değerlendirme Sistemi: Genel İşleyiş

> Durum: **Taslak v0.3** (D1, D3, D5 işlendi; `CheckDef` öneri alanları, `layer` yalnız A/B, iki kapsam kavramı netleştirildi) · Kapsam: kullanıcı bir web sitesi girer, sistem onu değerlendirir ve rapor üretir.
> Bu belge bir **tasarım belgesidir**; kaynak projeden alınanlar `[K]`, bizim kararlarımız `[B]`, henüz karar verilmemiş noktalar `[?]` ile işaretlidir.
> Referanslar: kaynak analizi notları (notlar) ve `kaynak/` (kaynak). Bölüm 12'de her dayanak iddia kaynak kodla yeniden doğrulanmıştır.

---

## 1. Amaç ve sınırlar

### 1.1 Sistem ne yapar
Orijinal kaynak proje gibi **iki mod** sunar `[K, doğrulandı]`:
- **Site denetimi** (`seo-audit` karşılığı): tek **Health Score**, 7 kategori, site genelinde bulgular.
- **Sayfa analizi** (`seo-page` karşılığı): tek URL için **Page Score Card**, 5 kategori. Detay §9.

Bir kullanıcı bir URL girer. Sistem:
1. siteyi güvenli şekilde çeker ve (gerekirse) render eder,
2. deterministik kurallarla ölçer,
3. ölçülenden **tekrarlanabilir** bir skor ve bulgu listesi üretir,
4. LLM ile yorum, öncelik ve öneri metni ekler,
5. kullanıcıya rapor olarak sunar ve geçmişle karşılaştırır.

### 1.2 Bu belge neyi kapsar / kapsamaz
| Kapsar | Kapsamaz (sonraki belgeler) |
|---|---|
| Değerlendirme modeli: katmanlar, bulgu, skor, güven, kapsam | Crawl/fetch altyapısı ve SSRF (02) |
| Bulgu şeması ve kural kaydı | Ajan/iş kuyruğu orkestrasyonu (03) |
| Skor formülü, kapı, sürümleme | Veri modeli ve depolama (04) |
| LLM'in değerlendirmedeki yeri | API ve rapor arayüzü (05) |
| Test ve kalibrasyon stratejisi | Kimlik doğrulama, faturalama, kiracılık |

## 2. Tasarım ilkeleri

| # | İlke | Gerekçe |
|---|---|---|
| P1 | **Skoru kod hesaplar, LLM hesaplamaz.** `[B]` | kaynak projede Health Score'u kod değil LLM üretir; aynı site iki kez farklı skor alabilir `[K, doğrulandı]` |
| P2 | **Ölçmediğini skorlama.** `[K+B]` | kaynak proje bunu yalnız backlink'te uyguluyor (4/7 faktör kapısı); biz genel kural yapıyoruz |
| P3 | **Her puan kesintisinin id'si ve kanıtı olur.** `[K]` | `page_checks.py` modeli: `{id, severity, message, evidence, count}` |
| P4 | **Dürüst etiketleme.** `[K]` | Sezgisel eşikler ("title 60 karakter") Google kuralı değildir; bulgu bunu söyler |
| P5 | **Sürümlü kurallar ve skor.** `[B]` | Kural veya ağırlık değişince eski raporlar karşılaştırılabilir kalmalı |
| P6 | **Kanıtsız LLM iddiası skora girmez.** `[B]` | Tekrarlanabilirlik ve güvenilirlik |
| P7 | **Sayfa içeriği güvenilmeyen veridir.** `[K]` | Prompt injection: sayfadan gelen metin talimat sayılmaz |
| P8 | **Zarif bozulma.** `[B]` | Bir kaynak (PSI, render) yoksa rapor üretilir, o kısım "ölçülmedi" olur |

## 3. Genel akış

```
 URL girişi
    │
    ▼
┌──────────────┐   reddedilirse → hata raporu (SSRF/erişilemez)
│ 1. Doğrula   │
│  + güvenli   │
│    fetch     │
└──────┬───────┘
       ▼
┌──────────────┐
│ 2. Render    │  raw HTML → SPA şüphesi (is_spa) → headless render → js_gap
│ + iş tipi    │  iş tipi: saas | local | ecommerce | publisher | agency | other
└──────┬───────┘
       ▼
┌────────────────────────────────────────────────────────────┐
│ 3. ÖLÇÜM (kod, deterministik) = Katman A                    │
│   page_checks · transport · robots · sitemap · schema ·     │
│   görsel · PSI/CrUX · AI crawler erişimi                    │
│   çıktı: facts + findings[] + not_checked[]                 │
└──────┬─────────────────────────────────────────────────────┘
       ▼
┌────────────────────────────────────────────────────────────┐
│ 4. HEURİSTİK (kod, düşük güven) = Katman B                  │
│   şablonlu metadata, filler/tekrar, atıf boşluğu            │
└──────┬─────────────────────────────────────────────────────┘
       ▼
┌────────────────────────────────────────────────────────────┐
│ 5. SKORLAMA (kod)                                           │
│   kategori skoru → yeniden normalize → kapı → genel skor    │
│   + kapsam % + güven                                        │
└──────┬─────────────────────────────────────────────────────┘
       ▼
┌────────────────────────────────────────────────────────────┐
│ 6. YORUM (LLM) = Katman C                                   │
│   E-E-A-T / SXO "danışma skoru", öneri metni, öncelik,      │
│   aksiyon planı. Genel skoru DEĞİŞTİRMEZ.                   │
└──────┬─────────────────────────────────────────────────────┘
       ▼
 7. Rapor (JSON → HTML/PDF) + geçmişle karşılaştırma (drift)
```

## 4. Üç değerlendirme katmanı

| Katman | Kim üretir | Örnek | Genel skora etkisi | Güven |
|---|---|---|---|---|
| **A. Deterministik** | Kod | `missing-title`, `noindex`, `tls-cert-expired`, `html-over-2mb`, CWV eşikleri | **Belirler** | yüksek |
| **B. Heuristik** | Kod | şablonlu description, tekrar oranı, atıf boşluğu, `thin-content` | Kategoriyi en fazla ±10 puan ayarlar `[B]` | orta/düşük |
| **C. Yargı** | LLM | E-E-A-T, arama niyeti uyumu, öneri metni | **Girmez**; ayrı "danışma skoru" `[B]` | düşük, etiketli |

**Neden C skora girmiyor?** Aynı içerik farklı çalıştırmada farklı E-E-A-T bandı alabilir. Skora girerse kullanıcı "değişiklik yapmadım ama skor düştü" der ve güven biter. Danışma skoru kullanıcıya gösterilir ama "tahmini" diye etiketlenir ve trend takibine alınmaz.

### 4.0 Dil bağımlılığı ve Katman B (karar D5) `[B]`

Heuristik kalıp listeleri (`content_quality.py`, `metadata_template.py`) İngilizce'dir `[K]`. Türkçe için yazılana kadar **Katman B kapalıdır**: bulgu üretmez, skoru ayarlamaz, `not_checked` listesine "dil desteklenmiyor" gerekçesiyle yazılır.

Ek bulgu: Katman A'daki iki kontrol de dile bağlıdır. `page_checks.py` `STOPWORDS` sabiti yalnızca İngilizce sözcük içerir (`a, about, the, ...`) `[doğrulandı]`; `title-not-reflected-in-content` ve `description-not-reflected-in-content` bu listeyle "anlamlı sözcük" çıkarır. Türkçe'de `ve, bir, için, ile` gibi sözcükler elenmez, oran bozulur ve yanlış pozitif üretir. Bu yüzden:

| Kontrol | Durum |
|---|---|
| `title-not-reflected-in-content` | **Kapalı**, Türkçe stopword listesi gelene kadar `not_checked` |
| `description-not-reflected-in-content` | **Kapalı**, aynı gerekçe |
| `thin-content` | Açık. Kelime sayımı dilden bağımsızdır; `words_measurable` boşluksuz diller (zh/ja/th) için zaten devre dışı bırakır `[K]` |
| Diğer 44 kontrol | Açık, HTML/header tabanlı, dilden bağımsız |

Sayfa dili `lang` özniteliğinden veya içerikten tespit edilir. Desteklenmeyen dil → dile bağlı kontroller kapalı, rapor "bu dilde X kontrol yapılamadı" der (kapsam etkilenir, §8.4).

### 4.1 Katman C'nin tekrarlanabilirlik önlemleri `[B]`
- Rubrik bantları sabit eşlemeli (Güçlü/Orta/Zayıf/Yok → 90/65/35/10).
- Zorunlu kanıt alıntısı: alıntı sayfada yoksa bulgu reddedilir.
- Sıcaklık 0, JSON Schema ile doğrulanmış çıktı.
- Önbellek anahtarı: `içerik_hash + rubrik_sürümü + model_id`.
- Ham HTML modele verilmez, yalnız çıkarılmış alanlar verilir (P7).

## 5. Kural kaydı (Check Registry)

Her kontrol tek bir kayıttır; kod, doküman ve test bu kayıttan türer. `[K: page_checks.CHECKS sözlüğü]`

```ts
type CheckDef = {
  id: string;                 // kararlı, kebab-case: "missing-title"
  category: CategoryId;       // hangi kategoriye ceza yazar
  layer: "A" | "B";
  scope: "page" | "site";
  severity: Severity;         // başlangıç; bağlamla düşürülebilir (bkz. 7.3)
  message: string;            // sabit metin, sayfadan gelen veri içermez
  heuristic: boolean;         // true ise "Google kuralı değil" notu gösterilir
  thresholds?: Record<string, number>;
  requires?: ("headers" | "rendered" | "psi" | "robots" | "sitemap")[];
  since: string;              // kural sürümü
  // Öneri alanları (v0.3): deterministik, LLM'siz; bkz. belge 03 §7.1
  message_key: string;        // çevrilebilir bulgu metni anahtarı (TR/EN)
  recommendation_key: string; // standart öneri metni anahtarı
  effort_default: "S" | "M" | "L";
  impact_default: "low" | "medium" | "high";
  depends_on?: string[];      // başka kural kimlikleri (statik grafik)
  failure_check_key: string;  // "başarısız olduğunu nasıl anlarız" şablonu
  leading_indicator_key: string;
  references?: string[];      // birincil kaynak bağlantıları
};
```

Bu alanlar sayesinde her Katman A/B bulgusunun eksiksiz bir önerisi LLM'siz vardır; Katman C yalnız bağlam cümlesi ekler. Şablonu eksik kuralın bulgusu **öneri değil gözlem** olarak raporlanır `[K: "dört evreden geçmemiş öneri bulgudur"]`.

Önemli kural `[K]`: bir kontrol `requires` ihtiyacını karşılayamazsa **bulgu üretmez**, `not_checked` listesine `{id, reason}` yazar. Örnek: HTTP header'ı yoksa `noindex-header` "ölçülmedi" olur, "geçti" sayılmaz.

### 5.1 Başlangıç kümesi
`page_checks.py` içindeki 47 kontrolün tamamı başlangıç değeri olarak alınır `[K]`: Critical 2 (`noindex`, `noindex-header`), High 6 (`missing-title`, `canonical-points-elsewhere`, `uses-frames`, `placeholder-text`, `mixed-content`, `html-over-2mb`), Medium 24, Low 15. Tam liste: `kaynak analizi notları 02-scoring-evaluation-system.md`.

Eklenecekler `[B]`:
- `transport_check.py` bulguları: `tls-cert-expired`, `tls-cert-hostname-mismatch`, `tls-cert-not-trusted`, `tls-handshake-failed`, `hsts-missing`, `csp-missing` vb.
- Site düzeyi: robots.txt, sitemap geçerliliği, redirect zinciri.
- Schema: JSON-LD tip/zorunlu alan doğrulaması, deprecated tip uyarısı (HowTo vb.).
- Performans: LCP/INP/CLS eşikleri (`good ≤2.5s/≤200ms/≤0.1`, `poor >4s/>500ms/>0.25`) `[K, doğrulandı]`.

## 6. Bulgu şeması

Üç ayrı bulgu şekli var kaynakta (audit, `page_checks`, drift) `[K, 08]`. Biz tek şekle indiriyoruz `[B]`:

```json
{
  "id": "canonical-points-elsewhere",
  "rule_version": "1.0",
  "category": "technical",
  "layer": "A",
  "severity": "High",
  "scope": "page",
  "url": "https://example.com/a",
  "message": "Canonical başka bir URL'yi işaret ediyor...",
  "evidence": "https://example.com/b",
  "count": 1,
  "heuristic": false,
  "confidence": "high",
  "recommendation": null,
  "effort": null,
  "impact": null
}
```

- **`layer` yalnız `A` veya `B`'dir** (v0.3 düzeltmesi). Katman C **bulgu üretmez**: ürettiği şeyler (a) bulguya bağlı bağlam cümlesi (`finding_advice`), (b) danışma skoru (`advisory_scores`) ve (c) sınırlı gözlemlerdir (belge 03, belge 04). Bu, bulguların tamamen deterministik ve değiştirilemez kalmasını sağlar.
- `recommendation`, `effort`, `impact` ölçüm aşamasında **kural kaydındaki varsayılanlardan** (`recommendation_key`, `effort_default`, `impact_default`) doldurulur; Katman C bunları değiştirmez, yalnız `finding_advice` ile bağlam ekler.
- `evidence` kırpılır (200 karakter) ve sayfadan geldiği için güvenilmeyen etiketlidir `[K]`.
- `severity` değişirse orijinali ve gerekçeyi saklarız: `severity_original`, `severity_reason`.

## 7. Kategoriler, ağırlıklar ve iş tipi

### 7.1 Kategoriler `[B, K'dan uyarlandı]`
| Kategori | kaynak proje | Bizde varsayılan | Ana kaynak (Katman A) |
|---|---|---|---|
| Teknik / indekslenebilirlik | 22 | 25 | durum kodu, robots, canonical, noindex, TLS, redirect, sitemap |
| Sayfa içi | 20 | 20 | title, description, H1, heading, URL, lang, viewport, OG |
| İçerik | 23 | 20 | kelime sayısı, thin, tekrar, okunabilirlik (A+B) |
| Schema | 10 | 10 | JSON-LD geçerlilik ve tip kontrolü |
| Performans | 10 | 10 | PSI/CrUX alan verisi |
| AI arama hazırlığı | 10 | 10 | AI crawler robots, SSR/js_gap, yapı |
| Görseller | 5 | 5 | alt, boyut, lazy-LCP |

kaynak projedeki 22/23/20/10/10/10/5 dağılımı yalnız SKILL.md metninde geçer, kodda hiçbir yerde uygulanmaz `[doğrulandı]`. Bizim sapmamız: Teknik'i artırdık (indekslenemeyen sitede diğer her şey anlamsız), İçerik'i azalttık (en öznel kategori, deterministik kısmı küçük).

### 7.2 İş tipi profilleri `[B]`
Tespit sinyalleri kaynak projeden: SaaS (`/pricing`, `/features`), yerel (telefon, adres), e-ticaret (`/cart`, Product schema), yayıncı (`/blog`, Article schema), ajans (`/case-studies`).

| Kategori | Varsayılan | E-ticaret | Yerel | Yayıncı | SaaS |
|---|---|---|---|---|---|
| Teknik | 25 | 22 | 22 | 25 | 25 |
| Sayfa içi | 20 | 18 | 20 | 18 | 20 |
| İçerik | 20 | 15 | 18 | 27 | 22 |
| Schema | 10 | 15 | 12 | 10 | 8 |
| Performans | 10 | 12 | 10 | 8 | 10 |
| AI arama | 10 | 8 | 8 | 7 | 10 |
| Görseller | 5 | 10 | 10 | 5 | 5 |

`[?]` Bu sayılar başlangıç tahminidir. Kalibrasyon yapılana kadar **yalnız varsayılan profil** kullanılır, iş tipi yalnız etiket olarak gösterilir. Profiller kalibrasyondan sonra açılır.

### 7.3 Bağlamla severity ayarı `[B]`
Kod, severity'yi şu kurallarla düşürebilir (LLM değil):
- `missing-meta-description`: sayfa `noindex` ise Info'ya düşer.
- `thin-content`: sayfa tipi biliniyorsa `quality-gates` eşiği kullanılır `[K]` (blog 1500, ürün 400, ana sayfa 500...); tip bilinmiyorsa 200 kelime ve Low `[B]`.
- Her düşürme `severity_reason` ile kayda geçer.

## 8. Skor hesaplama

### 8.1 Kategori skoru
```
ceza(f)     = taban(severity) × kapsam(f)
kapsam(f)   = 1.0                                              sayfa düzeyi, tek örnek
            = min(1, 0.4 + 0.6 × etkilenen_sayfa_oranı)        site düzeyi
            = min(1, 0.5 + 0.5 × log10(1+count)/log10(1+20))   sayfa içi sayım (alt'sız görsel vb.)
ham_ceza(c) = Σ_severity min( severity_tavanı , Σ_id min(id_tavanı , ceza(f)) )
skor(c)     = max(0, 100 − ham_ceza(c))
```

| Severity | Taban | id tavanı | Kategori başına severity tavanı |
|---|---|---|---|
| Critical | 40 | 40 | 100 |
| High | 15 | 15 | 60 |
| Medium | 6 | 6 | 30 |
| Low | 2 | 2 | 10 |
| Info | 0 | 0 | 0 |

**Saturasyonun amacı:** 500 sayfada aynı Low sorun 500 kez cezalanmaz; 100 Low bulgu 1 Critical'a eşit olmaz. `[B]` Katsayılar başlangıç değeridir `[?]` kalibre edilecek.

### 8.2 Genel skor
```
ağırlık'(c) = w(c) / Σ_{ölçülen k} w(k)
ham_genel   = Σ_{ölçülen c} ağırlık'(c) × skor(c)
kapsam      = Σ_{ölçülen c} w(c) / Σ_{uygulanabilir c} w(c) × 100   (0-100)
genel       = min(ham_genel, kritik_tavan)
```

**Uygulanabilir kategori** (v0.3 netleştirmesi): site modunda yedi kategorinin hepsi uygulanabilirdir, ölçülmeyen kategori kapsamı düşürür. Sayfa modunda Page Score Card'daki beş kategori uygulanabilirdir; Performans ve AI arama yalnız o veri varsa (PSI/CrUX, robots/`js_gap`) uygulanabilir sayılır, aksi halde kartı hiç görünmez ve kapsamı düşürmez (belge 01 §9).

**İki ayrı kapsam kavramı** karıştırılmamalıdır: `scores.coverage_pct` **kategori** kapsamıdır (burada tanımlı); `crawl.coverage` **sayfa** kapsamıdır (planlanan/çekilen/render edilen sayfa, belge 05 §9.4). İkisi birbirinden bağımsız raporlanır, ikisi de güveni etkiler (§8.5).

### 8.3 Kapı (gate)
| Koşul | Tavan |
|---|---|
| Ana URL'de `noindex`/`noindex-header`, `status ≥ 400`, `tls-cert-expired`, `tls-cert-hostname-mismatch`, `tls-cert-not-trusted` | 40 |
| `canonical-points-elsewhere` ana URL'de, veya robots.txt tüm siteyi engelliyor | 70 |
| Diğer | 100 |

Kapı etkinse rapor en üstte yazar: "Skor şu nedenle sınırlandı: `<id>`". Gerekçe: indekslenemeyen siteye 85 puan göstermek kullanıcıyı yanıltır.

### 8.4 Kapsam kuralı
- `kapsam ≥ 60`: sayısal skor + "Kapsam %X" birlikte gösterilir.
- `kapsam < 60`: sayısal skor **gösterilmez**, "Yetersiz veri" yazılır `[K: backlink 4/7 kuralından]`.
- Ölçülmeyen kategori raporda gri kart olur ve nedeni yazar ("PSI anahtarı yok", "render başarısız").

### 8.5 Güven (confidence)
Her kategori ve genel skor bir güven etiketi taşır:
- **yüksek**: tüm bulgular Katman A, veri tam
- **orta**: Katman B düzeltici etkin veya örneklem sınırlı (<30 sayfa)
- **düşük**: büyük bölüm `not_checked` veya render başarısız

## 9. Skor birimleri: site denetimi ve sayfa analizi `[K, karar D1]`

Orijinal yapı korunur: iki mod, iki ayrı skor kartı. `seo-audit` site genelinde tek Health Score verir (`skills/seo-audit/SKILL.md`); `seo-page` tek URL için ayrı bir Page Score Card verir (`skills/seo-page/SKILL.md`) `[doğrulandı]`.

| | Site denetimi | Sayfa analizi |
|---|---|---|
| Giriş | Alan adı / ana URL | Tek URL |
| Çıktı | **Health Score** | **Page Score Card** |
| Kategoriler | 7: Teknik, Sayfa içi, İçerik, Schema, Performans, AI arama, Görseller | 5: Sayfa içi, İçerik, Teknik, Schema, Görseller `[K]` |
| Bulgu kapsamı | site düzeyi + örneklenen sayfalar | yalnız o sayfa |
| Kapı (§8.3) | Ana URL'e göre | O URL'e göre |

Kaynaktaki Page Score Card'da Performans ve AI arama yoktur, çünkü sayfa HTML'inden ölçülemezler (CWV "reference only") `[K]`. Biz bunu şöyle uyarlıyoruz `[B]`: sayfa modunda da PSI/CrUX verisi varsa Performans kartı eklenir, yoksa kart hiç görünmez (ölçülmedi kuralı, §8.4).

**Site denetimi hesabı** `[B]`: Health Score, aynı kategori formülünü (§8.1) iki girdiyle kullanır:
- site düzeyi bulgular (robots, sitemap, TLS, redirect, tekrarlayan şablon sorunları),
- örneklenen sayfaların bulguları (aynı `id` birden çok sayfada ise `kapsam(f)` etkilenen sayfa oranına göre büyür, id tavanı korunur).

Ek olarak raporda sayfa dağılımı gösterilir: "sayfaların çeyreği şu skorun altında" (P25), çünkü ortalama kötü sayfaları gizler.

Örneklem: ana sayfa + sitemap/iç linklerden seçilen en fazla N sayfa. `[?]` N, crawl bütçesine bağlıdır ve belge 05'de kararlaştırılacak.

## 10. Zaman içi değişim (drift)

Skoru etkilemez `[B]`; ayrı uyarı akışıdır `[K: 17 kural]`.
- Baseline: ilk denetim anlık görüntüsü; sonraki denetimler karşılaştırılır.
- Kural seviyeleri: CRITICAL 8 (`noindex_added`, `canonical_changed`, `canonical_removed`, `schema_removed`, `h1_removed`, `h1_changed`, `title_removed`, `status_code_error`), WARNING 6, INFO 3 `[K, doğrulandı]`.
- `score_version` değiştiyse skor trendi çizilmez, yalnız bulgu farkı gösterilir (eski ve yeni skor kıyaslanamaz).

## 11. Başarısızlık modları

| Durum | Sistem davranışı |
|---|---|
| URL reddedildi (özel IP, geçersiz) | Skor yok, hata raporu |
| Site erişilemez / timeout | Skor yok, hata + yeniden dene önerisi |
| robots.txt botu engelliyor | Erişilebilen sayfalar analiz edilir, kısıt rapora yazılır, kapı 70 |
| Render başarısız | Raw HTML ile devam, `js_gap` ve render bazlı kontroller `not_checked` |
| PSI/CrUX yok | Performans "ölçülmedi", kapsam düşer |
| LLM başarısız/şema dışı | Skor etkilenmez; danışma bölümü "üretilemedi" |
| Sayfada prompt injection | Bulgu olarak raporlanır, talimat yürütülmez `[K]` |
| Kural sürümü değişti | Yeni `score_version`, eski raporlar yeniden hesaplanmaz |

## 12. Doğrulama matrisi (notlar ↔ kaynak)

Bu belgeye dayanak olan iddialar kaynak kodla yeniden kontrol edildi.

| İddia | Kaynak kontrolü | Sonuç |
|---|---|---|
| `page_checks.py` 47 kontrol | `CHECKS` sözlüğü AST ile sayıldı | ✅ 47 |
| Dağılım Critical 2 / High 6 / Medium 24 / Low 15 | `SEVERITY_OVERRIDES` + ton eşlemesi uygulandı | ✅ tam eşleşme |
| Critical: `noindex`, `noindex-header` | `SEVERITY_OVERRIDES` | ✅ |
| Drift 17 kural: 8 / 6 / 3 | `drift_compare.py` seviye atamaları sayıldı | ✅ |
| Health Score'u kod hesaplamıyor | `scripts/` ve `tests/` genelinde arandı; yalnız `google_report.py` gösterir, `validate_backlink_report.py` backlink'e özel | ✅ |
| 22/23/20/10/10/10/5 ağırlıkları kodda yok | Kodda aranıp bulunamadı | ✅ yalnız SKILL.md metninde |
| CWV eşikleri (2.5s/200ms/0.1; 4s/500ms/0.25) | `pagespeed_check.CWV_THRESHOLDS` ve `cwv-thresholds.md` | ✅ |
| Başlık 30-60, description 120-160 | `page_checks.py` sabitleri ve `quality-gates.md` | ✅ (heuristik etiketli) |
| `html-over-2mb` High | `CHECKS` (attention → High) | ✅ |
| TLS bulgu id'leri (`tls-cert-expired` vb.) | `transport_check.py` | ✅ id'ler mevcut |
| `not_checked` mekanizması | `page_checks.run_checks` içinde `skip()` | ✅ |
| "Skor kalibrasyonu yok" | Kaynakta korelasyon/kalibrasyon kodu bulunamadı | ✅ (kaynak bilerek heuristik diyor) |
| İki mod: site denetimi ve sayfa analizi | `seo-audit` (Health Score, site geneli) ve `seo-page` (Page Score Card) SKILL.md | ✅ (v0.1'deki "kaynak tanımlamıyor" ifadesi yanlıştı, düzeltildi) |
| Page Score Card 5 kategori | `seo-page/SKILL.md` "Output" bölümü | ✅ On-Page, Content, Technical, Schema, Images |
| `STOPWORDS` yalnız İngilizce | `page_checks.py:236` | ✅, Türkçe'de relevance kontrolleri bozulur |
| Boşluksuz diller için kelime sayımı kapısı | `page_checks.words_measurable` | ✅ zh/ja/th/lo/km/my |

**Doğrulanmadı / bu turda okunmadı:** `transport_check.py` içindeki her bulgunun severity'si; `content_quality.py` iç formülleri (Katman B için bu belgede taban olarak kullanılmadı, Faz 2b'de ayrıca ele alınacak; Katman B Türkçe'de zaten kapalı, bkz. §4.0); drift kural eşiklerinin tamamı.

## 13. Test ve kalibrasyon stratejisi

### 13.1 Test `[K deseni]`
- Her kontrol id'si için **üç fixture**: POSITIVE (tetiklenir), NEAR_MISS (eşiğin hemen altında, tetiklenmez), CLEAN (hiç bulgu yok).
- Skor fonksiyonu saf olduğu için birim testi: aynı bulgu listesi → aynı skor (property-based test: bulgu ekleme skoru artıramaz).
- Altın dosya (golden) testleri: sabit bir HTML + header seti → sabit JSON çıktı; `rule_version` değişirse bilinçli güncelleme.
- Düşmanca girdi: aşırı büyük HTML, derin DOM, bozuk JSON-LD, sahte talimat metni.
- "Bilinen yanlış ifadeler" regresyon listesi (ör. "FID", "HowTo schema öner").

### 13.2 Kalibrasyon `[?]`
Ağırlıklar ve cezalar şu an tahmindir. Plan:
1. 20-30 gerçek site seç (farklı iş tipleri, bilinen iyi/kötü).
2. Manuel uzman denetimi ile 1-5 puan.
3. Skorlar arası sıralama korelasyonu (Spearman) ölç; hedef ≥ 0.7.
4. Sapmaları ceza tabanı ve ağırlıkla düzelt, `score_version` artır.

## 14. Açık kararlar (bir sonraki adımdan önce netleşmeli)

| # | Karar | Öneri | Etki |
|---|---|---|---|
| D1 ✅ | Sayfa mı site mi birincil çıktı? | **Karar: orijinaldeki gibi iki mod.** Site denetimi → Health Score, sayfa analizi → Page Score Card (§9) | Veri modeli, UI |
| D2 | `kapsam < 60` eşiği ve "Yetersiz veri" davranışı | 60 | Kullanıcı deneyimi |
| D3 ✅ | Danışma skoru (LLM) kullanıcıya gösterilsin mi? | **Karar: evet**, "tahmini" etiketli, trend ve Health Score dışında (§4) | Güven, maliyet |
| D4 | İş tipi profilleri ilk sürümde açık mı? | Hayır, yalnız etiket | Kalibrasyon yükü |
| D5 ✅ | Türkçe içerik heuristikleri | **Karar: Katman B Türkçe listeler yazılana kadar kapalı**; dile bağlı 2 Katman A kontrolü de kapalı (§4.0) | İçerik kategorisi |
| D6 | PSI anahtarı kullanıcıdan mı bizden mi? | Bizden (kota izlenir) | Maliyet |
| D7 | Örneklem büyüklüğü N | Belge 05'de (crawl) | Kapsam, maliyet |

## 15. Sonraki belgeler

| Belge | Konu | Bu belgeden devraldığı |
|---|---|---|
| [`02-agent-arhitecture.md`](02-agent-arhitecture.md) | İş hattı, kuyruk, orkestrasyon, LLM katmanı, Q&A | Katman A/B/C ayrımı, `requires`/`not_checked`, kapı ve skor aşaması |
| [`03-rubrik-and-prompts.md`](03-rubrik-and-prompts.md) | Katman C rubrikleri, sinyal kataloğu, prompt'lar, doğrulayıcılar | Katman C sınırı, danışma skoru, `CheckDef` öneri alanları |
| [`04-data-model.md`](04-data-model.md) | Tablolar, DDL, değiştirilemezlik | Bulgu şeması (§6), skor (§8), kural/skor sürümleri |
| [`05-system-design.md`](05-system-design.md) | Güvenli fetch, render, örneklem, genel sistem | `requires`, `not_checked` gerekçe kodları, D7 |
| [`06-io-schemas.md`](06-io-schemas.md) | API ve rapor JSON şeması | Skor çıktısı, kapsam, güven |
| [`07-features.md`](07-features.md) | Özellik kataloğu, planlar | İki mod, danışma skoru, kapsam kuralı |
| [`08-file-structure.md`](08-file-structure.md) | Dosya ve modül yapısı | Kural kaydı, saf çekirdek ilkesi |
| [`09-implementation-roadmap.md`](09-implementation-roadmap.md), [`10-decision-log.md`](10-decision-log.md) | Faz planı, karar günlüğü | Çıkış kriterleri, açık kararlar |
