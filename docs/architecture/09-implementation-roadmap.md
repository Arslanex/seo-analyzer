# 09. Uygulama Yol Haritası: Faz Faz Plan

> Durum: **Taslak v0.1** · Girdi: belge 00-08 · Bu belge **uygulamanın sırasını** belirler; mimari kararları değiştirmez.
> İşaretler: `[K]` kaynak proje · `[B]` bizim kararımız · `[?]` açık karar
> Büyüklükler **göreli** (S < M < L < XL). Takvim tahmini verilmez: ekip büyüklüğü ve hızı bilinmiyor, uydurma tarih vermek yanıltıcı olur. Faz 0-1 ölçüldükten sonra gerçek hız verisiyle takvim çıkarılır.

---

## 1. İlkeler

| # | İlke | Sonuç |
|---|---|---|
| R1 | **Her faz, kullanıcıya veya içeride bir hedefe değer üretir** ve tek başına çalışır | Faz sonunda demo edilebilir bir şey var |
| R2 | **Önce deterministik çekirdek, LLM en son** | Faz 1'de LLM yok; ürün LLM'siz de değerlidir |
| R3 | **Gerileme kalkanı önce gelir**: bir yetenek taşınmadan kaynağın testi yeşil olmalı | Belge 00 §4 |
| R4 | **Riskli varsayımlar önce prototiplenir** (Faz 0) | DNS pin, kuyruk, render izolasyonu |
| R5 | **Güvenlik, özellikten önce**: SSRF ve egress kontrolü açılmadan dış istek yapan hiçbir özellik yayınlanmaz | Belge 05 §5 |
| R6 | **Sürümleme baştan**: `rule_version` ve `score_version` ilk satırdan | Belge 01 P5 |
| R7 | **Her faz sonunda belgeler ve parity tablosu güncellenir** | Sessiz kayıp yok |
| R8 | **Kapsam eklemek, kapsam çıkarmaktan pahalıdır**: yeni modül eklemeden önce çekirdek metrikleri (doğruluk, maliyet) ölçülür | `kaynak analizi notları 09` §5 |

## 2. Faz haritası

```
Faz 0  Temel + prototipler ──────────────────────────────┐
  │                                                      │
  ▼                                                      │
Faz 1  Sayfa analizi, uçtan uca, LLM'siz  (alfa)         │ prototip sonuçları
  │                                                      │ D13 (kuyruk) kararı
  ▼                                                      │
Faz 2a Site modu + render + PSI  ◀───────────────────────┘
  │
  ▼
Faz 2b LLM katmanı + Q&A + BYOK + Türkçe
  │
  ▼
Faz 2c Schema üretimi (kopyala-yapıştır JSON-LD)   ──▶  GENEL YAYIN (beta)
  │
  ▼
Faz 3  İzleme + doğrulanmış sahip + GSC + PDF
  │
  ▼
Faz 4+ Genişleme (backlink, yerel, e-ticaret, hreflang, görsel, ...)
```

| Faz | Büyüklük | Kullanıcı değeri | Dış istek yapar mı | LLM |
|---|---|---|---|---|
| 0 | M | yok (içeride) | yalnız test | yok |
| 1 | L | tek URL için skor ve bulgu raporu | evet (sınırlı alfa) | yok |
| 2a | L | tüm site örneklemi + performans | evet | yok |
| 2b | L | yorum, öneri, soru-cevap | evet | evet |
| 2c | M | hazır JSON-LD düzeltmeleri | – | kısmen |
| 3 | XL | zamanlı izleme, değişim uyarıları, Google verisi, PDF | evet | evet |
| 4+ | XL | genişletilmiş modüller | evet | evet |

## 3. Depo yapısı ve araçlar (Faz 0'da kurulur)

```
seo-analyzer/
├── pyproject.toml            # uv / pip, ruff, mypy, pytest
├── NOTICE                    # kaynak proje MIT telif ve atıf (portlanan dosyalar listeli)
├── src/seoa/
│   ├── safefetch/            # policy.py, resolver.py (SafeResolver), fetcher.py, limits.py, encoding.py
│   ├── parse/                # html.py, jsonld.py
│   ├── checks/               # registry.py, page/*.py, transport.py, robots.py, sitemap.py, schema.py
│   ├── crawl/                # normalize.py, discovery.py, sampling.py, politeness.py
│   ├── render/               # spa.py, js_gap.py, browser.py
│   ├── scoring/              # weights.py, score.py, gate.py, versions.py
│   ├── llm/                  # client.py, modules/, prompts/, cache.py, budget.py
│   ├── pipeline/             # stages.py, orchestrator.py, workers.py
│   ├── report/               # schema.py (audit.json), html/, templates/
│   ├── api/                  # app.py, routes/, schemas/
│   └── db/                   # models.py, migrations/ (Alembic)
├── tests/
│   ├── unit/ · golden/ · hostile/ · parity/ · integration/ · e2e/
│   └── fixtures/             # HTML/header/robots/sitemap örnekleri (portlanan + yeni)
└── docs/                     # bu belgeler
```

| Araç | Amaç | Not |
|---|---|---|
| `ruff`, `mypy` (strict çekirdekte) | Biçim, tip | Kaynak da ruff kullanıyor, py311, satır 100 `[doğrulandı: pyproject.toml]` |
| `pytest` (+ `pytest-asyncio`, `hypothesis`) | Test | `hypothesis` skor özellik testleri için |
| CI | lint + tip + birim + hostile + parity her PR'da | Parity/hostile ayrı iş, hızlı geri bildirim |
| Alembic | DB göçleri | Belge 04 |
| `pre-commit` | Hızlı yerel kontrol | |

**Atıf kuralı `[K]`:** kaynak projeden taşınan her dosyanın başlığında kaynak yolu ve MIT notu bulunur; `NOTICE` dosyası tüm listeyi tutar. CC BY-SA kaynaklı kalıp listeleri **taşınmaz** (belge 00 §6).

## 4. Faz 0: Temel ve prototipler

**Amaç:** riskli varsayımları ucuza çürütmek veya doğrulamak; sonraki fazların üzerine basacağı iskeleti kurmak.

### 4.1 Teslimatlar

| # | Teslimat | Ayrıntı |
|---|---|---|
| 0.1 | Repo iskeleti, CI, lint/tip/test, NOTICE | §3 |
| 0.2 | **`safefetch` çekirdeği** | `policy.py` (kaynaktaki `is_safe_ip`, engelli hostname'ler, authority-confusion reddi, DNS64 istisnası, `normalize_hostname` portu), `resolver.py` (`aiohttp` `SafeResolver`), limitler (10 MiB, 64 KiB redirect gövdesi, 5 redirect, süre) |
| 0.3 | **SSRF politika test paketi** | Kaynağın `test_url_safety*.py` vakaları **`SafeResolver` adaptörüyle yeniden yazılmış** (kaynak testler `getaddrinfo` yamasına bağlı, değişmeden çalışmaz) `[doğrulandı: belge 08]`. `_port_pin` testleri kapsam dışı (yerel hedef izin listesi alınmıyor). Yeni vakalar: rebinding yarışı, redirect → private, gzip bombası |
| 0.4 | Pydantic modelleri | `Finding`, `NotChecked`, `CategoryScore`, `AuditJSON` (belge 06'teki şema) |
| 0.5 | Kural kaydı iskeleti | `CheckDef` (belge 01 §5), kayıt/keşif mekanizması |
| 0.6 | DB çekirdek şeması + ilk Alembic göçü | Belge 04'ün Faz 0-1 tabloları |
| 0.7 | **Prototip raporları** (ayrı kısa belgeler) | P1-P4 (§4.2) |
| 0.9 | **Sonuç yazma yolu ve e2e test dikişi** | Fetch/Render → nesne depolamaya ön imzalı yazma + Redis akışı → Control sonuç alıcı (belge 02 §3.2). E2E testlerde yerel test sitesi özel IP'de olduğundan SSRF politikası onu reddeder; kaynak bunu `LOCAL_TARGETS` ile çözüyordu, biz almıyoruz. Çözüm: **`FixtureFetcher` enjeksiyonu** (belge 08), üretim yolunda yerel hedef izni **yok** |
| 0.8 | `parity/` iskeleti | Parity vakalarını **kaynak test dosyalarından çıkaran** araç ve beklenen bulgu id/severity eşlemesini yükleyen koşucu (kaynakta hazır fixture kütüphanesi yok: `tests/fixtures/` yalnız 2 dosya, `test_page_checks.py` HTML'i satır içi) |

### 4.2 Prototipler (bu fazın asıl değeri)

| # | Soru | Yöntem | Başarı ölçütü | Başarısızsa |
|---|---|---|---|---|
| **P1** ✅ *(kısmi, bkz. `docs/prototypes/P1-safe-resolver.md`: IP-literal resolver'ı atlar, ön doğrulama şart; gerçek TLS/SNI ve redirect fetcher kaldı)* | `SafeResolver` doğrula-sonra-bağlan yarışını gerçekten kapatıyor mu? Redirect hedefleri de geçiyor mu? TLS/SNI bozulmuyor mu? | Yerel sahte DNS sunucusu (ilk sorguda public, sonra private IP), yönlendirme zinciri, IPv6 | Tüm kaynak hostile testleri yeşil + rebinding simülasyonunda özel IP'ye **hiç bağlantı denemesi yok** | Alternatif: bağlantıyı doğrulanmış IP'ye kurup `Host`/SNI'yı elle ayarlama; son çare egress proxy'ye tam güven |
| **P2** | Arq gereksinimlerimizi karşılıyor mu: gecikmeli iş, **lease/yeniden alma**, öncelik, çökme sonrası devralma | Worker'ı iş ortasında öldür; fan-in yarışı; 1000 sahte iş | Çökme sonrası iş **tam bir kez etkili** tamamlanır (idempotency ile); **Redis Streams** üzerinden sonuç teslimi (çift teslim, tüketici çökmesi) aynı testte sınanır; gecikmeli `finalize_fetch` doğru tetiklenir | Celery veya Dramatiq; veya Postgres tabanlı kuyruk (D13) |
| **P3** | Render worker'ı egress firewall arkasında güvenli ve yeterince hafif mi? | Playwright konteyneri, özel aralığa çıkış denemesi, bellek/eşzamanlılık ölçümü | Özel aralık **ağ seviyesinde** reddedilir; render başına bellek ve süre ölçülür, belge 05 §7.4'teki tahminler güncellenir | Render'ı Faz 2a'dan ayırıp ertele; ham HTML ile devam |
| **P4** | Redis semafor + token bucket hedef-host sınırını kiracılar arası doğru uyguluyor mu, çökmede kilit sızdırıyor mu? | 100 eşzamanlı denetim, tek hedef, worker çökmesi | Hedefin gördüğü istek hızı sınırın altında; çöken worker'ın lease'i süre sonunda serbest kalır | Postgres advisory lock veya daha basit sabit sınır |

### 4.3 Çıkış kriterleri (Faz 0 bitti sayılır eğer)
- [ ] Kaynağın SSRF politika vakaları (yeniden yazılmış hâliyle) yeni uygulamaya karşı **yeşil**.
- [ ] P1-P4 raporları yazıldı; **D13 (kuyruk) ve D12 (render) kararları kesinleşti**.
- [ ] CI yeşil; boş bir "merhaba" denetimi (`validate → fetch_entry`) uçtan uca çalışıyor.
- [ ] `NOTICE` ve atıf süreci yerinde.

### 4.4 Riskler
| Risk | Etki | Azaltma |
|---|---|---|
| P1 başarısız (resolver çözümü yetersiz) | SSRF güvenliği | Egress proxy'yi **birincil** savunma yap, uygulama içi kontrolü ikincil tut |
| Prototiplerin sonucu mimariyi değiştirir | Belge 02 revizyonu | Beklenen: bu yüzden Faz 0 var |

## 5. Faz 1: Sayfa analizi, uçtan uca, LLM'siz (alfa)

**Amaç:** "bir URL gir, deterministik bir rapor al" akışını **uçtan uca** çalıştırmak. LLM yok. Bu, ürünün omurgasıdır.

### 5.1 Kapsam

| Alan | İçerik |
|---|---|
| Giriş | URL normalizasyonu (belge 05 §4), SSRF doğrulama, giriş fetch, redirect zinciri |
| Ölçüm | **47 `page_checks` kontrolü** (Türkçe'de 2'si kapalı, belge 01 §4.0), `transport_check` (TLS, header, HTTP→HTTPS), robots.txt (giriş URL'i için), JSON-LD sözdizimi + tip/zorunlu alan doğrulaması (deprecated liste: HowTo, FAQ rich result durumu) `[K]`, görsel kontrolleri |
| Skor | Belge 01 §8: kategori skoru, kapı, kapsam, güven; **Page Score Card** (5 kategori) |
| Rapor | `audit.json` (şema doğrulamalı) + HTML rapor (TR/EN) |
| API | `POST /v1/audits` (mode=page), `GET /v1/audits/{id}`, `GET .../report`, SSE ilerleme; tek kiracı + API anahtarı |
| Altyapı | Control + Fetch + Analyze + Report worker'ları (Render/LLM yok) |
| Güvenlik | Egress proxy, dış istek denetim kaydı, bot kimliği + bilgi sayfası **(D10 şart)** |

### 5.2 Kapsam dışı (bilinçli)
Site modu, render, PSI/CrUX, LLM, Q&A, çok kiracılılık/RLS, doğrulama, PDF.

### 5.3 Çıkış kriterleri
- [ ] **Parity:** kaynak fixture'larıyla `page_checks` çıktısı bulgu id ve severity bakımından **aynı** (farklar belgelenmiş: Türkçe'de kapalı 2 kontrol).
- [ ] **Determinizm:** aynı girdi → aynı skor (property testi: bulgu eklemek skoru artıramaz; kapsam<60 → sayı yok).
- [ ] **Golden testler:** en az 20 gerçek-benzeri sayfa (SSR, SPA kabuğu, noindex, canonical başka yere, mixed content, 2 MB üstü HTML, Türkçe karakterli, bozuk JSON-LD).
- [ ] **Hostile testler** CI'da; SSRF reddi denemeleri kayıt altında.
- [ ] Performans: sayfa analizi p95 < 20 sn (LLM'siz) **ölçüldü** ve belge 02 §14 güncellendi.
- [ ] Alfa kullanıcı grubu (kapalı) gerçek sitelerle denedi; yanlış pozitif listesi tutuldu.
- [ ] `00-capability-parity.md` Faz 1 satırları güncel.

### 5.4 Faz 1'de ölçülecek (Faz 2'nin girdisi)
Kontrol başına yanlış pozitif oranı; Türkçe sitelerde başlık/description uzunluk eşiklerinin uygunluğu (`kaynak analizi notları 02` §15.4 ve belge 01 §7.3); gerçek sitelerde skor dağılımı (ceza tabanı kalibrasyonu için ilk veri).

### 5.5 Riskler
| Risk | Etki | Azaltma |
|---|---|---|
| Kural yanlış pozitifleri kullanıcı güvenini kırar | Ürün itibarı | Kapalı alfa; her bulgu `heuristic` etiketi ve kanıtı gösterir; "bildir" düğmesi |
| Skor kalibrasyonsuz | Anlamsız sayı | Alfada sayıyı "deneysel" etiketle; Faz 2'de kalibrasyon çalışması |
| Dış istek yapan alfa kötüye kullanılır | Hukuki/itibar | Kapalı davet, kota, istek kaydı, bot sayfası (D10, D16) |

## 6. Faz 2a: Site modu, render, PSI/CrUX

**Amaç:** siteyi örnekleyip tüm site skoru vermek; performans ve AI-hazırlık kategorilerini ölçmek.

### 6.1 Kapsam
- **Keşif ve örneklem** (belge 05 §9): robots `Sitemap:`, yaygın yollar, iç linkler; şablon kümeleme; tabakalı, tohumlu örneklem; **çekirdek/keşif** ayrımı; kullanıcı tanımlı URL'ler.
- **Nezaket ve bütçe** (belge 05 §10, belge 02 §8): Redis semafor + token bucket, devre kesici, bütçe nesnesi, kısmi sonuç.
- **Fan-out/fan-in** (belge 02 §4.3), akıtılan ölçüm, deadline.
- **Render:** `_is_spa`, `js_gap`, K≤5 sayfa; egress-izole render worker.
- **PSI + CrUX:** performans kategorisi; anahtar yoksa "ölçülmedi".
- **AI arama hazırlığı (deterministik kısım):** robots AI bot erişimi (RFC 9309 grup seçimi `[K: agentic_check.parse_robots]`), `js_gap`, llms.txt varlığı (isteğe bağlı sinyal, Google'ın yok saydığı notuyla `[K]`).
- **Site modu skoru:** Health Score (7 kategori), sayfa dağılımı (P25), kapsam raporu.
- **Çok kiracılılık:** tenants/users, kotalar, RLS (belge 04), `usage_ledger`.
- **Katman mantığı:** `sites.tier` ve katmana bağlı bütçe kodda hazır: doğrulanmamış 25, doğrulanmış 50 (üst sınır 200). Doğrulama akışı Faz 3'te; Faz 2a'da alfa kullanıcıları elle `verified` işaretlenir (D11).

### 6.2 Çıkış kriterleri
- [ ] 25 ve 50 sayfalık örneklem denetimleri p95 < 3 dk (LLM'siz), hedef host'un gördüğü istek hızı sınır altında (yük testi).
- [ ] **Çökme dayanıklılığı testi:** worker öldürülür, denetim devralınır, sonuç aynı.
- [ ] **Örneklem determinizmi:** aynı tohum → aynı sayfalar; çekirdek skor iki çalıştırmada aynı.
- [ ] Kapsam raporu doğru (planlanan/çekilen/render edilen/atlanan nedenleriyle).
- [ ] Egress firewall **dağıtım testi**: render worker'dan özel aralığa bağlantı başarısız (belge 05 §13).
- [ ] **Kalibrasyon çalışması v1:** 20-30 siteyle uzman skoru vs sistem skoru; Spearman ≥ 0.7 hedefi (belge 01 §13.2); ceza tabanları ve ağırlıklar güncellenir, `score_version` artar.
- [ ] D8 (robots giriş istisnası) ve D10 kapatılmış.

### 6.3 Riskler
| Risk | Etki | Azaltma |
|---|---|---|
| Render pahalı/güvensiz | Maliyet, güvenlik | K≤5, P3 sonuçları, egress firewall zorunlu; render kapatılabilir bayrak |
| Örneklem temsil gücü zayıf | Yanıltıcı skor | Kapsam ve güven etiketi; tek şablon örneği → güven düşük (belge 05 §9.4) |
| Hedef siteye yük | İtibar/hukuk | Nezaket sınırları, kiracılar arası host sınırı, devre kesici |

## 7. Faz 2b: LLM katmanı, Q&A, BYOK, Türkçe

**Amaç:** deterministik rapora yorum, öneri ve etkileşim eklemek; Türkçe desteğini tamamlamak.

### 7.1 Kapsam
- **Katman C modülleri** (belge 02 §9): `content_eeat`, `ai_readiness_commentary`, `synthesize`; kanıt doğrulama, şema doğrulama, önbellek, bütçe, `llm_calls`.
- **Aksiyon planı:** severity + effort/impact (kural kaydından deterministik varsayılan) + `depends_on`; 4 faz (belge 06).
- **Q&A** (belge 02 §10, belge 00 §3.2) ve **modül yeniden çalıştırma** (belge 02 §11).
- **BYOK** (belge 00 §3.4): şifreli saklama, maskeli ipucu, yalnız Katman C.
- **Türkçe (L7)** (belge 00 §3.5): stopword listesi (lisans kontrolü), filler/CTA kalıpları, doğrulama kümesi; açılış kriteri sağlanınca iki Katman A kontrolü ve Katman B Türkçe için açılır.
- **Plan katmanları ve LLM kotası.**
- **Paylaşılabilir rapor bağlantısı (F-33, IO3):** imzalı, süreli, `noindex`.
- **Bulgu geri bildirimi (F-23, FT7):** "bu bulgu yanlış" düğmesi, kural bazında sayaç; Faz 1 alfa verisinin kalıcı hâli.

### 7.2 Çıkış kriterleri
- [ ] **Kanıt doğrulaması:** LLM çıktısındaki her alıntı sayfa metninde mevcut; aksi halde reddedilir (test: kasıtlı uydurma içerikli sahte yanıt).
- [ ] **Prompt injection testleri:** talimat içeren sayfa → bulgu olarak raporlanır, yürütülmez; Q&A'da `evidence` içindeki talimat yok sayılır.
- [ ] **Maliyet:** ortalama denetim LLM maliyeti ölçüldü ve plan sınırlarıyla uyumlu; bütçe aşımında `partial`.
- [ ] **Önbellek isabet oranı** ölçüldü; aynı girdi LLM'i tekrar çağırmıyor.
- [ ] **Q&A:** atıfsız iddia reddi, rapor dışı soru reddi, token tavanı testleri.
- [ ] **BYOK:** anahtar hiçbir log/hata mesajı/DB düz metin alanında yok (sızıntı taraması testi).
- [ ] **Türkçe:** yanlış pozitif oranı kabul eşiğinin altında (eşik Faz 1 verisinden belirlenir `[?]`).
- [ ] D3 (danışma skoru) arayüzde "tahmini" etiketli ve genel skora girmiyor (test).

### 7.3 Riskler
| Risk | Azaltma |
|---|---|
| LLM çıktısı tutarsız | Sıcaklık 0, rubrik bantları, önbellek, şema doğrulama; danışma skoru skor dışı |
| Maliyet kontrolden çıkar | Katman C yalnız K≤5 sayfada, tavanlar, kota, küçük model varsayılanı |
| Prompt injection | Belge 02 §9.3; araçsız/ağsız model; kanıt doğrulaması |

## 8. Faz 2c: Schema üretimi

**Amaç:** kullanıcıya "kopyala-yapıştır" JSON-LD düzeltmeleri vermek (belge 00 §2.3: öncelikli).

- `schema_generate.py`'nin yüksek etkili tip üreticileri portlanır `[K]`; hangi tiplerin portlandığı **taşıma sırasında kaynaktan doğrulanır** `[?]`.
- Üretilen JSON-LD **doğrulanır** (kendi validator'ımızdan geçer) ve placeholder içermez; deprecated tipler asla önerilmez (HowTo; FAQ rich result Google'da sona erdi, bu yüzden yeni FAQPage önerilmez `[K: seo/SKILL.md]`).
- Çıkış: üretilen her örnek doğrulayıcıdan geçer; kaynak testleri yeşil.

> **MVP notu:** aşağıdaki önkoşullardan hukuki gözden geçirme, operatör paneli ve gizlilik/silme akışı **MVP için zorunlu değildir** (belge 10 §1.1); ürünleşme kararına bırakılır. SSRF/egress ve bütçe önlemleri teknik olduğu için geçerlidir.

**Faz 2c sonunda genel yayın (beta):** kullanıcıya site/sayfa denetimi, yorum, Q&A, düzeltme örnekleri sunulur. **Önkoşullar:** D16 (kötüye kullanım politikası) yürürlükte, bot sayfası canlı, egress firewall dağıtım testinden geçmiş, kalibrasyon v1 yapılmış, **operatör paneli (F-83) ve gizlilik/silme akışı (F-85)** hazır (FT5), hukuki gözden geçirme (gizlilik/KVKK, kullanım şartları) tamamlanmış `[?]`.

## 9. Faz 3: İzleme, doğrulanmış sahip, Google verisi, PDF

### 9.1 Kapsam
| Bileşen | İçerik | Bağımlılık |
|---|---|---|
| **Site doğrulama (D11)** | DNS TXT / meta etiketi / dosya; `site_verifications`; **tier=verified** (50-200 sayfa, daha yüksek hız) | – |
| **Zamanlı izleme** | `monitoring_schedules`, zamanlayıcı, çekirdek + dönen keşif örneklemi (belge 00 §3.3) | Doğrulama |
| **Drift** | `drift_baselines`, `drift_events`, 17 kural portu `[K]`; ayrı uyarı akışı | Çekirdek örneklem |
| **Bildirim** | E-posta/webhook | |
| **GSC (L2)** | OAuth web akışı, URL Inspection (indeks durumu, Google'ın seçtiği canonical), fail-closed property çözümü `[K: google_properties]`; kiracı izolasyonu | Doğrulama |
| **PDF** | Playwright `page.pdf()` (önce) veya WeasyPrint (belge 06 kararı) | Rapor şablonu |
| **Geçmiş/trend arayüzü** | Yalnız aynı `score_version` içinde trend; çekirdek skor | |

### 9.2 Çıkış kriterleri
- [ ] Drift: kaynağın drift testleri (`test_drift_*.py`) yeşil; 17 kuralın tamamı bizim şemada çalışıyor.
- [ ] Trend: örneklem değişse de çekirdek skor karşılaştırılabilir (test).
- [ ] GSC: yanlış site eşlemesi **reddedilir** (fail-closed testi); tokenlar şifreli.
- [ ] Doğrulama: sahte doğrulama denemeleri başarısız (testi).
- [ ] PDF: rapor kalite kapısı (belge 06) geçer.

## 10. Faz 4+: Genişleme

Sırayla değerlendirilir; **her biri ayrı karar ve ayrı ölçümle** açılır (R8). Sıra, kullanıcı talebi ve maliyetle belirlenir:

| Adaylar (belge 00 §2.3) | Not |
|---|---|
| `seo-hreflang` tam denetim | Çok dilli siteler |
| Görsel ekran görüntüsü, mobil test | Depolama maliyeti |
| `seo-agentic` (agent-readiness tam) | Standartlar oturdukça |
| Backlink (Common Crawl, Moz, Bing) | Harici kaynak/maliyet |
| Yerel SEO / harita, e-ticaret | Dikey ürünler |
| SXO, cluster, content-brief, competitor-pages, programmatic, plan, flow | Üretim/strateji odaklı, SERP verisi gerekir |
| DataForSEO, Ahrefs, SE Ranking, Profound, Bing, Matomo, Unlighthouse | Ücretli/harici |

## 11. Kapı kararlar (faz başlamadan kapanmalı)

| Karar | Kapanması gereken en geç | Neden |
|---|---|---|
| D10 Bot adı + bilgi sayfası | Faz 1 alfa | Dış istek yapan ilk sürümden itibaren kimlik şart |
| D13 Kuyruk | Faz 0 sonu | Faz 1 worker'ları buna dayanır |
| D12 Render barındırma | Faz 0 sonu | Faz 2a |
| D8 Robots giriş istisnası | Faz 2a | Site modu keşfi |
| D16 Kötüye kullanım politikası | Genel yayın (Faz 2c sonu) | Hukuki risk |
| D11 Sahiplik doğrulama | Faz 3 başı (tier mantığı Faz 2a'da kodda hazır) | Kota |
| D2 / D4 / D6 | Faz 2a kalibrasyonu | Eşikler ve profiller veriyle |
| D15 SLO | Faz 1 sonu | Ölçüm sonrası |

## 12. Çalışma sözleşmesi (her faz için)

1. **Faz başı:** kapsam ve çıkış kriterleri bu belgeden alınır; değişen varsayım belgeye yazılır.
2. **Faz içi:** her PR'da lint + tip + birim + hostile + parity yeşil.
3. **Faz sonu:** (a) çıkış kriterleri işaretlenir, (b) `00-capability-parity.md` ve `10-decision-log.md` güncellenir, (c) belge 01-08'de sapmalar düzeltilir, (d) bir sonraki fazın riskli varsayımları için prototip gerekiyorsa listelenir.
4. **Sapma kuralı:** mimariden sapan bir uygulama kararı, **önce** ilgili belgede güncellenir, sonra kodlanır.
5. **Gerileme kuralı:** hiçbir çıkış kriteri, bir önceki fazın testlerini kırarak karşılanmaz.

## 13. Kapsam dışı (tüm fazlarda şimdilik)

Faturalama/ödeme, kimlik doğrulama sağlayıcısı (SSO/OAuth girişi; yalnız minimal API anahtarı/oturum), ayrı SPA arayüzü (sunucu tarafı HTML ile başlanır; TypeScript arayüz ileride belge 06 D-kararına bağlı), mobil uygulama, beyaz etiket, çok bölgeli dağıtım.

## 14. Doğrulama matrisi

| İddia | Kontrol | Sonuç |
|---|---|---|
| Kaynak `ruff`, `py311`, satır 100 kullanıyor | `pyproject.toml` | ✅ |
| Kaynak testleri (url_safety, page_checks, transport, drift, content_quality, backlink kapısı) mevcut | `tests/` dizini | ✅ varlık; **`test_hostile_inputs.py` SSRF testi değil, url_safety testleri yamaya bağlı, `fixtures/` 2 dosya** (belge 08 ve belge 00 §4 düzeltmesi) |
| Kaynakta `schema_generate.py` mevcut, yüksek etkili tipler için üretici | CLAUDE.md açıklaması + dosya | ✅ varlık; **hangi tipler** doğrulanmadı |
| Drift 17 kural, SQLite | `drift_compare.py`, `drift_baseline.py` | ✅ kural sayısı (belge 01 §12); şema ayrıntısı belge 04'te |
| `google_properties` fail-closed property çözümü | `scripts/google_properties.py` (05 raporu) | ✅ varlık; ayrıntı satır satır okunmadı |

## 15. Sonraki adım

Mimari belgeler (00-10) tamamlandı. Uygulama **Faz 0** ile başlar: önce P1-P4 prototipleri ve `safefetch` çekirdeği.

**Uygulamaya geçmeden önce açık onay gereken kapı kararlar** (belge 10 §11): **D10** (bot adı ve alan adı, Faz 1 alfa için şart) ve **D8** (robots giriş URL'i istisnası, Faz 2a için). Bunlar Faz 0'ı **bloklamaz**; Faz 0 yalnız dahili prototiplerden oluşur ve dış hedefe istek yapmaz (yalnız yerel sahte sunucular).

**Faz 0 başlangıç kontrol listesi:**
1. Depo iskeleti ve CI (belge 08 §3, §12).
2. `safefetch/policy.py` portu ve `SafeResolver` (belge 05 §5.2).
3. P1-P4 prototipleri; sonuçlarla belge 02/05/10 güncellenir (D12, D13).
4. Portlama haritası (belge 08) Faz 0-1 satırlarının ilk dosyaları: `page_checks`, `parse_html`, `transport_check`, `sitemap_discovery`.
5. `NOTICE` ve atıf süreci (belge 00 §6).

## 16. MVP profili (kullanıcı kararlarına göre)

Kullanıcı kararları (belge 10 §1.1, §2): **tek kullanıcı, yerel makine, sunucu HTML, hukuki süreç yok**. Bu profil faz kapsamlarını **küçültür**, güvenlik temellerini küçültmez.

| Konu | Tam mimari (belge 02-08) | MVP profili |
|---|---|---|
| Kullanıcı/kiracı | Çok kiracılı, RLS, kotalar | **Tek kullanıcı**; `tenant_id` kolonu şemada kalır (tek sabit kiracı), RLS ve kota **kapalı** |
| Kimlik doğrulama | API anahtarı/oturum | **Yok** (yalnız `localhost`'a bağlanır) |
| Çalışma ortamı | Konteyner filosu, Z1-Z3 bölgeleri | **docker-compose**: PostgreSQL + Redis; worker'lar yerel süreç; Z3 ayrımı yok |
| Egress firewall | Zorunlu (render öncesi) | **Zorunlu değil**; SSRF politikası ve `SafeResolver` **kodda zorunlu kalır** |
| Render | İzole worker | Yerel Playwright, K≤5 |
| Sonuç yazma yolu (belge 02 §3.2) | Nesne depolama + Redis akışı | **Basitleştirilir:** fetch worker'ları yerel süreç olduğu için doğrudan DB'ye yazabilir; arayüz (`ResultSink`) korunur, ürünleşmede akış uygulanır |
| Nesne depolama | S3 uyumlu | **Yerel dosya sistemi** (`./data/objects/`), aynı anahtar düzeni |
| Planlar/katmanlar | free/pro/team, tier | **Tek profil**; N yapılandırma değeri (varsayılan 50, üst sınır 200) |
| Doğrulama (D11) | DNS TXT/meta | **Yok** |
| BYOK | Şifreli anahtar saklama | **Yok**: `ANTHROPIC_API_KEY` ortam değişkeni |
| Operatör paneli, paylaşım bağlantısı, PDF | Faz 2b/2c/3 | **MVP dışı** |
| Zamanlı izleme, drift, GSC | Faz 3 | **MVP dışı** |

**MVP fazları (yeniden kesilmiş):**

| MVP aşaması | İçerik | Başarı ölçütü ("çalışıyor mu?") |
|---|---|---|
| **M0** | Faz 0: iskelet, `safefetch`, P1 (resolver), P2 (kuyruk, yerel) | SSRF politika testleri yeşil; kuyrukta çökme sonrası devralma çalışıyor |
| **M1** | Faz 1: sayfa analizi uçtan uca, LLM'siz, sunucu HTML rapor | Gerçek 10+ URL'de rapor üretiyor; yanlış pozitif listesi tutuluyor |
| **M2** | Faz 2a: site modu, örneklem, render, PSI | 50 sayfalık denetim < 3 dk; çekirdek skor tekrarlanabilir |
| **M3** | Faz 2b: Katman C, Q&A | Kanıt doğrulama ve enjeksiyon testleri yeşil; maliyet/denetim ölçülüyor |
| **M4** | Faz 2c: schema üretimi | Üretilen JSON-LD doğrulayıcıdan geçiyor |

Faz 3 ve sonrası MVP sonucuna göre (çalışıyorsa) planlanır. **Çıkış kriterleri** ilgili fazlarla aynıdır; yalnızca çok kiracılılık, RLS, kota ve firewall maddeleri MVP'de uygulanmaz.

### 16.1 Uygulama sapmaları (MVP inşası sırasında verilen kararlar)

| Konu | Önceki karar | Uygulanan | Neden |
|---|---|---|---|
| Kod konumu | `seo-analyzer-mvp/seo-analyzer/` | **Depo kökü** (`seo-analyzer-mvp/`); `kaynak/` ve `docs/` yan yana | Kullanıcı yapıyı kökte düzleştirdi; `.env` de kökte |
| Veritabanı | PostgreSQL | **SQLite** (`aiosqlite`, WAL), belge 04 şemasının MVP alt kümesi | Docker kapalı, `psql`/Redis yok; sıfır altyapıyla çalışsın |
| Kuyruk/worker | Redis + Arq | **Süreç içi asyncio kuyruğu** + worker görevleri | Aynı nedenle; `AuditService` arayüzü korunur, ürünleşmede kuyruk takılır |
| Nesne depolama | S3 uyumlu | `data/objects/` (gzip HTML) | Yerel |
| Varsayılan LLM | belirtilmemişti | **`claude-haiku-5-5`**, `effort=low`, yapılandırılmış çıktı | Çağrı başına ≈ $0.00005; yeterli kalite deneyle ölçülür |
| Sıcaklık | "sıcaklık 0" (belge 03 §12) | **Gönderilmez** | Yeni modellerde `temperature/top_p/top_k` 400 döner; determinizm = önbellek + şema + sabit rubrik |
| LLM bütçesi | – | **Kalıcı defter, sert tavan $8** (kullanıcı limiti $10) | `data/llm_ledger.json`, `SEOA_LLM_BUDGET_USD` |
| `ruff` kapsamı | – | `kaynak/`, `docs/`, `data/` hariç | Kökte çalıştırılan `ruff`, referans kaynağın 166 dosyasını biçimlendirmişti (yalnız biçim, doğrulandı) |

