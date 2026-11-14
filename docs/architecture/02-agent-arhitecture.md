# 02. Agent Mimarisi: İş Hattı, Worker'lar, Orkestrasyon, LLM Katmanı

> Durum: **Taslak v0.2** (§3.2 sonuç yazma yolu eklendi) · Önceki belgeler: [`01`](01-evaluation-system.md), [`05`](05-system-design.md), [`00`](00-capability-parity.md)
> İşaretler: `[K]` kaynak projeden alındı · `[B]` bizim kararımız · `[?]` açık karar · `[doğrulandı]` kaynak kodla kontrol edildi
> Yığın: Python ≥ 3.11, FastAPI, PostgreSQL, Redis, Arq (asyncio worker), aiohttp, Playwright (async). **Kütüphane seçimleri `[B]` önerisidir; Faz 0'da kısa bir prototiple doğrulanacaktır.** Tablo ve enum adları belge 04'teki sözleşmeyle aynıdır.

---

## 1. Bu belgenin görevi

Belge 01 neyi ölçeceğimizi, belge 05 veriyi nasıl toplayacağımızı tanımladı. Bu belge, **ölçümü zamanda nasıl yürüttüğümüzü** tanımlar: iş parçalarının sırası, paralellik, hata/yeniden deneme, bütçe, LLM çağrıları, soru-cevap ve zamanlanmış izleme.

kaynak projede bu işi bir **LLM orkestratörü** yapar: SKILL.md prompt'u hangi ajanın ne zaman çalışacağını söyler, Claude Code `Agent` aracıyla alt ajanları başlatır `[doğrulandı: skills/seo-audit/SKILL.md]`. Biz bunu **koda** taşıyoruz (belge 00, L3 ve belge 01 P1): orkestrasyon deterministik bir durum makinesidir; LLM yalnız Katman C'de ve Q&A'da, sınırlı ve doğrulanmış biçimde çalışır.

## 2. Kaynaktan alınanlar ve alınmayanlar

| Kaynak deseni | Karar | Not |
|---|---|---|
| **Koşullu uzman tetikleme tablosu** (iş tipi + yetenek/kimlik tespiti → hangi ajan çalışır) | **Alınır**, **kodla** | Kaynakta karar LLM'e bırakılmış `[doğrulandı: seo-audit SKILL.md adım 4]`; biz kural motoru yaparız (tekrarlanabilir ve ucuz) |
| **Kısmi bulgu yazma (partial → complete)** | **Alınır** | Kaynak: ajan `maxTurns` bütçesine çarpabilir; her ajan ilk geçişten sonra `findings/*.md` yazar, bitirirken üzerine yazar `[doğrulandı: seo-audit SKILL.md "Error Handling"]`. Bizde: `audits.status=partial` ve her aşama checkpoint'i |
| **Fan-out / fan-in** (en çok 17 paralel ajan) | **Alınır**, havuz ve oran sınırıyla | Kaynakta eşzamanlılık sınırı yok; "17" yalnız dokümandaki bir tavandır. API'de RPM/TPM ve maliyet nedeniyle zorunlu sınır gerekir |
| **Model katmanlaması** (5 ajan Opus, geri kalanı Sonnet) | **Uyarlanır** | `[doğrulandı: agents/*.md model alanı: cluster, content, drift, geo, sxo = opus]`; gerekçe yalnız CHANGELOG'da "judgment-heavy". Bizde varsayılan küçük model, derin analiz plana bağlı |
| **Inline fallback** (alt ajan yoksa sıralı çalıştır) | **Alınmaz** | Bizde her zaman kuyruk |
| **Merge'in LLM prompt'una bırakılması** | **Alınmaz** | Skor ve birleştirme kodla (belge 01 §8) |
| **Dosya sistemi çıktıları** (`{domain}-audit/findings/*.md`) | **Dönüştürülür** | Veritabanı satırları + nesne depolama |
| 429/retry/devre kesici | **Kaynakta yok** `[doğrulandı: belge 05 §2]` | Sıfırdan tasarlanır (§8) |

## 3. Bileşen mimarisi

```
                           ┌────────────────────────────┐
 Kullanıcı ── HTTPS ─────▶ │ API (FastAPI)              │──┐
                           │ kimlik, kota, doğrulama    │  │ okur/yazar
                           └───────┬─────────┬──────────┘  │
                       enqueue     │         │ SSE         ▼
                                   ▼         │       ┌───────────┐
                           ┌──────────────┐  │       │ PostgreSQL│  durum, bulgu,
                           │ Redis        │◀─┘       │           │  skor, kota
                           │ kuyruk, kilit│          └─────▲─────┘
                           │ oran sınırı  │                │
                           │ pub/sub      │                │
                           └──┬───┬───┬───┘                │
        ┌─────────────────────┘   │   └──────────────┐     │
        ▼                         ▼                  ▼     │
 ┌─────────────┐         ┌───────────────┐   ┌─────────────┴─┐
 │ Control     │         │ Fetch workers │   │ Analyze       │  saf fonksiyonlar,
 │ (orkestratör│         │ (aiohttp,     │   │ workers (CPU) │  süreç havuzu
 │  durum mak.)│         │  SafeResolver)│   └───────────────┘
 └─────────────┘         └──────┬────────┘   ┌───────────────┐
                                │            │ LLM workers   │  BYOK burada çözülür
        ┌───────────────┐       │            └───────┬───────┘
        │ Render workers│       │                    │
        │ (Playwright)  │       │                    ▼
        └──────┬────────┘       │            ┌───────────────┐
               │                │            │ LLM sağlayıcı │
               ▼                ▼            └───────────────┘
        ┌─────────────────────────────┐   ┌───────────────┐
        │ EGRESS PROXY / FIREWALL     │   │ Report workers│──▶ Nesne depolama
        │ özel aralıklara çıkış YASAK │   └───────────────┘    (HTML gövdeler,
        └──────────────┬──────────────┘                         rapor, PDF)
                       ▼
                   İnternet (hedef siteler)
```

### 3.1 Worker türleri ve sınırları

| Worker | Kuyruk | Ne yapar | Ağ bölgesi | Sırlara erişim | Ölçekleme sinyali |
|---|---|---|---|---|---|
| **Control** | `q_control` | Durum makinesi, aşama geçişleri, fan-in, bütçe, iptal | iç | DB | kuyruk uzunluğu (hafif) |
| **Fetch** | `q_fetch` | SSRF doğrulama, HTTP fetch, robots, sitemap, transport | **egress proxy üzerinden** | yok | bekleyen fetch işi |
| **Render** | `q_render` | Playwright render, `js_gap` | **egress proxy üzerinden, ayrı hesap** | **yok** | bekleyen render işi |
| **Analyze** | `q_analyze` | Katman A/B kontrolleri, skor, aksiyon planı iskeleti | iç, **dış ağ yok** | DB | CPU |
| **LLM** | `q_llm` | Katman C, Q&A | yalnız LLM sağlayıcısına | **BYOK çözme** | token/dk |
| **Report** | `q_report` | `audit.json` doğrulama, HTML/PDF üretimi | iç | nesne depolama | düşük |

Gerekçe: **Fetch ve Render** güvenilmeyen içerikle ve kullanıcı seçimli hedeflerle temas eder (belge 05 §5). Bu yüzden hiçbir sırra erişmez, ağları kısıtlıdır. **Analyze** dış ağa hiç çıkmaz. **LLM** worker'ı tek yerdir ki kullanıcı anahtarı çözülür ve sayfa içeriğiyle birlikte aynı süreçte başka hiçbir şey yapılmaz.

Eşzamanlılık varsayılanları `[?]` Faz 0-1'de ölçülüp ayarlanır: Fetch 50 görev/worker (I/O), Render 2 eşzamanlı bağlam/worker (belge 05 §7.4), Analyze = CPU çekirdek sayısı (süreç havuzu), LLM sağlayıcı oran sınırına göre.

### 3.2 Sonuçların yazılma yolu: sırsız worker'lar DB'ye yazmaz `[B]`

Fetch ve Render worker'ları güvenilmeyen içerikle temas eder ve **hiçbir sırra erişmez** (§3.1). Bu yüzden **veritabanı kimlik bilgisi taşımazlar**. Sonuçlarını şu yoldan teslim ederler:

```
Fetch/Render worker                      Control worker ("sonuç alıcı")
─────────────────                        ───────────────────────────────
1. Gövdeyi (HTML) nesne depolamaya  ──▶  (depoda: tenants/{t}/audits/{a}/pages/{p}/body…)
   yazar: yalnız-yazma, tek kullanımlık,
   yola ve boyuta kısıtlı ön imzalı URL
2. Sonuç meta verisini Redis akışına ──▶ 3. Şemayı doğrular (Pydantic), boyut/hash'i
   (stream) yazar: {audit_id, shard,        depodaki nesneyle karşılaştırır,
   status, headers, redirect_chain,         `audit_id`/`shard` yetkisini kontrol eder
   timing, body_ref, sha256, bytes}     ──▶ 4. DB'ye (`page_fetches`, `audit_pages`)
                                               idempotent UPSERT yazar, bütçeyi düşer
```

- **Neden:** ele geçirilmiş bir Fetch/Render worker'ı (örneğin Chromium açığı) en kötü ihtimalle **kendi göreviyle sınırlı bir nesne yazabilir** ve Redis akışına **geçersiz** bir kayıt düşürebilir; DB'ye, başka kiracının verisine veya LLM anahtarlarına erişemez. Doğrulama ve yazma yetkisi içeride, güvenilen Control tarafındadır.
- **Ön imzalı URL kapsamı:** tek nesne yolu, en çok `MAX_PAGE_BYTES` (10 MiB), kısa ömürlü; worker başka bir yola yazamaz.
- **Akış tüketimi:** Redis Streams üzerinde tüketici grubu; kayıt `XACK` edilmeden DB yazımı tamamlanmış sayılmaz. Çift teslim zararsızdır çünkü yazma idempotenttir (`UNIQUE(audit_id, stage, shard)`).
- **Kuyruk teknolojisi** (D13) Arq kalsa da akış ayrı bir Redis yapısıdır; P2 prototipi bunu da sınar (belge 09).
- Aynı desen Analyze/LLM worker'larına **uygulanmaz**: onlar iç ağdadır, sır taşırlar (LLM worker BYOK çözer) ve dar yetkili kendi DB rollerini kullanır (belge 04 roller).

## 4. Denetim yaşam döngüsü

### 4.1 Durum makinesi

```
              ┌──────────── iptal ────────────▶ canceled
              │
 queued ──▶ running ──▶ completed
              │   │
              │   └── bütçe/süre doldu, raporlanabilir sonuç var ──▶ partial
              │
              └── raporlanabilir sonuç yok ──────────────────────▶ failed
```

| Durum | Anlam | Kullanıcıya |
|---|---|---|
| `queued` | Kota alındı, kuyrukta | "Sırada" |
| `running` | En az bir aşama çalışıyor | İlerleme akışı |
| `completed` | Tüm aşamalar `done` veya `skipped` | Tam rapor |
| `partial` | Raporlanabilir ama eksik (bütçe, süre, kısmi örneklem, LLM başarısız) | Rapor + "kısmi" etiketi + nedenler |
| `failed` | Raporlanabilir sonuç yok (`target-rejected`, `unreachable`) | Hata raporu, skor yok |
| `canceled` | Kullanıcı iptal etti | Eldeki kısmi veri korunur, rapor üretilmez |

**Raporlanabilir** tanımı: giriş URL'i yanıt verdi (herhangi bir durum kodu, TLS hatası dahil) **ve** en az bir ölçüm yapılabildi. Giriş URL'i 4xx/5xx ise rapor üretilir, kapı 40 uygulanır (belge 01 §8.3). TLS el sıkışması başarısızsa yalnız transport bulguları vardır, kapsam düşük kalır ve belge 01 §8.4'e göre sayı yerine "Yetersiz veri" gösterilir; kapı banner'ı yine yazılır.

### 4.2 Aşamalar (DAG)

`stage` enum'u belge 04 ile aynıdır. Her satır idempotent bir iş birimidir.

| # | Aşama | Girdi | Çıktı (kalıcı) | Kuyruk | Paralellik | Başarısızlık politikası |
|---|---|---|---|---|---|---|
| 1 | `validate` | Kullanıcı girişi | normalize URL, kota ayrılması | control | 1 | Reddedilirse `failed` (`target-rejected`) |
| 2 | `fetch_entry` | URL | `page_fetches`, redirect zinciri, transport | fetch | 1 | Erişilemezse `failed`; TLS/4xx/5xx raporlanabilir |
| 3 | `robots` | origin | robots kuralları, sitemap URL'leri | fetch | 1 | 5xx → `robots-unreachable`, devam |
| 4 | `discovery` | robots + sitemap + ana sayfa linkleri | aday URL kümesi | fetch | sitemap başına 1 | Sitemap yok → `sitemap-missing`, devam |
| 5 | `sample` | aday küme, tier, tohum | `audit_pages` (`sample_kind`) | control | 1 | Hata olmaz (saf fonksiyon) |
| 6 | `fetch_pages` | örneklem | `page_fetches` | fetch | **sayfa başına 1 iş** (fan-out) | Sayfa hatası = o sayfa `error`; denetim devam |
| 7 | `render` | SPA şüpheli sayfalar | render sonucu, `js_gap` | render | ≤ K=5 sayfa | Hata → `render-failed`, ham HTML ile devam |
| 8 | `measure` | `page_fetches` | `findings`, `not_checked` (Katman A/B) | analyze | sayfa başına 1 + site düzeyi 1 | Kural istisnası → o kontrol `not_checked: rule-error`, **denetim durmaz** |
| 9 | `score` | `findings` | `category_scores`, `audit_scores` | analyze | 1 | Saf fonksiyon; hata = `failed` (kod hatası alarmı) |
| 10 | `advise` | çıkarılmış alanlar | `advisory_scores`, yorum bulguları (Katman C) | llm | modül × sayfa (K ≤ 5) | Hata → "üretilemedi", skor etkilenmez |
| 11 | `synthesize` | bulgular + skorlar | `top_findings`, `quick_wins`, aksiyon planı | llm + analyze | 1 | Hata → deterministik iskelet kalır |
| 12 | `report` | hepsi | `audit.json`, HTML | report | 1 | Şema doğrulaması başarısızsa `failed` + alarm (kod hatası) |

Sayfa modunda 3, 4, 5 atlanır (`skipped`), 6 yalnız giriş sayfasıdır.

**Sıralama notu:** 8 (measure) sayfa fetch'leri bittikçe **akıtılarak** başlayabilir (sayfa başına işler bağımsızdır); site düzeyi kontroller ve 9 yalnız fan-in sonrası çalışır. Bu, kullanıcıya erken ilerleme gösterir ve toplam süreyi kısaltır.

### 4.3 Fan-out / fan-in `[B]`

```
sample ──▶ [fetch_page(p1)] [fetch_page(p2)] ... [fetch_page(pN)]   (q_fetch, politeness sınırlı)
                │                  │                     │
                └──────────────────┴────────┬────────────┘
                                            ▼
                              finalize_fetch (fan-in)
```

- Her sayfa işi `audit_pages.status` günceller (`pending → fetched | failed | skipped`).
- **Fan-in:** her sayfa işi bitince `finalize_fetch` denenir; koşul "planlanan tüm sayfalar terminal durumda **veya** `fetch_deadline` geçti". Koşul sağlanınca tek kez çalışır (DB'de `UPDATE ... WHERE stage_status='running' RETURNING` ile kilitsiz tekilleştirme).
- **Son tarih (deadline):** Arq gecikmeli işi ile `fetch_deadline` anında `finalize_fetch` tetiklenir; geride kalan sayfalar `skipped: deadline` olur, kapsam buna göre düşer (`partial-sample`).
- Sayfa işleri **önceliklidir**: çekirdek örneklem (`core`) önce, keşif (`exploration`) sonra; bütçe dolarsa önce keşif feda edilir (belge 00 §3.3).

## 5. Orkestratör (Control worker)

### 5.1 İlkeler
1. **Durum veritabanındadır, bellekte değil.** Control worker çökerse başka bir worker `audit_stages` tablosundan kaldığı yerden devam eder.
2. **Her geçiş idempotenttir.** Anahtar: `(audit_id, stage, shard)`. Aynı iş iki kez çalışsa sonuç aynı satırlara yazılır (UPSERT, `UNIQUE(audit_id, stage, shard)`).
3. **Kilit/lease:** bir aşamayı çalıştıran worker `lease_until` yazar ve kalp atışı gönderir; süre dolarsa başka worker alır. Çift çalışma zararsızdır çünkü 2 geçerli.
4. **Orkestratörde LLM yoktur.** Karar mantığı kod (belge 01 P1, belge 00 L3).
5. **Aşama çıktıları değiştirilemezdir** (append-only); yeniden hesap yeni `audit` satırıdır (§12).

### 5.2 Koşullu modül tetikleme tablosu (kod) `[K'dan uyarlandı]`
Kaynak tablosu `skills/seo-audit/SKILL.md` adım 4'tedir; biz yalnız MVP'de anlamlı olanları alıp koşulu koda çeviriyoruz:

| Modül | Koşul | Faz |
|---|---|---|
| technical, onpage, schema, images, sitemap | her denetimde | 1 |
| performance | PSI anahtarı mevcut ve kota var (aksi halde `psi-unavailable`) | 2 |
| content (Katman B + C) | dil destekleniyor (belge 01 §4.0) | 2 |
| ai_readiness | her denetimde (robots AI botları, `js_gap`, yapı); yorum Katman C | 2 |
| drift | siteye ait baseline var | 3 |
| gsc/ga4 | doğrulanmış site + OAuth bağlı | 3 |
| local, ecommerce, backlinks, sxo, cluster | iş tipi/yetenek koşulu | 4+ |

Kaynaktaki `seo-visual`, `seo-agentic`, `seo-maps` vb. yukarıdaki tablonun ilgili fazlarına eşlenir (belge 00 §2.3).

## 6. Ölçüm aşaması (Katman A/B)

- Kontroller **saf fonksiyonlardır**: `check(page_ctx) -> list[Finding] | NotChecked`. Ağ ve zaman erişimi yoktur. Bu, golden test ve yeniden skorlamayı mümkün kılar (§12).
- `requires` (belge 01 §5) çözümlemesi tek yerde yapılır: gerekli kaynak yoksa kontrol çalıştırılmaz, `not_checked` yazılır.
- Kaynak `page_checks.run_checks` zaten bu biçimdedir (`findings`, `not_checked`, `summary`) `[doğrulandı]`; portlanır.
- **CPU-bağlı** olduğu için asyncio olay döngüsünü bloke etmesin diye süreç havuzunda çalışır (lxml/bs4 ayrıştırma). Sayfa HTML'i bellekte değil, nesne depolamadan akıtılır (10 MiB sınırı belge 05 §6).
- **Kural istisnası** denetimi durdurmaz: tek kontrol patlarsa `not_checked: rule-error` yazılır ve hata alarmı üretilir (bir kuralın yanlış kodlanması tüm denetimi öldürmemeli).

## 7. Skor aşaması

Saf fonksiyon: `score(findings, not_checked, weights, score_version) -> Scores` (belge 01 §8). Girdi hash'i (`input_hash`) ve `score_version` kaydedilir; aynı girdi → aynı çıktı. Çekirdek örneklem skoru ve keşif örneklemi ayrı hesaplanır (belge 00 §3.3).

## 8. Eşzamanlılık, nezaket ve bütçe

### 8.1 Katmanlı sınırlar

| Sınır | Anahtar | Değer (başlangıç `[B]`) | Uygulama |
|---|---|---|---|
| Hedef host başına eşzamanlılık | `host` | 2 | Redis semafor (lease TTL, çökmeye dayanıklı) |
| Hedef host başına hız | `host` | ≥ 500 ms aralık + jitter; `Crawl-delay` ≤ 10 sn | Redis token bucket |
| Hedef başına devre kesici | `host` | 5 ardışık 429/5xx/timeout → bu denetimde dur | DB + Redis |
| Kiracı eşzamanlı denetim | `tenant_id` | plana bağlı (ör. 2) | kota kontrolü `validate`'te |
| Kiracı günlük denetim | `tenant_id` | plana bağlı | `usage_ledger` |
| Küresel render eşzamanlılığı | – | worker sayısı × 2 | kuyruk |
| LLM eşzamanlılığı | sağlayıcı | sağlayıcı RPM/TPM'ine göre | token bucket |

**Önemli:** hedef host sınırı **kiracılar arası paylaşılır**. İki kullanıcı aynı siteyi aynı anda denetlerse hedef yine yalnız 2 eşzamanlı istek görür. Bu hem nezaket hem kötüye kullanım önlemidir.

### 8.2 Bütçe nesnesi (`audits.budget`, belge 04)

```json
{
  "max_pages": 50,
  "max_render_pages": 5,
  "max_bytes": 209715200,
  "max_wall_ms": 300000,
  "llm": {"max_tokens": 60000, "max_cost_usd": 0.50, "pages": 5},
  "tier": "unverified"
}
```

Bütçe `validate` aşamasında `tier` ve plandan **türetilir**; kullanıcı girişi bütçeyi artıramaz. Her tüketim noktası bütçeyi azaltır ve aşıldığında ilgili aşama `partial` olarak kapanır, nedeni `not_checked`/kapsam alanına yazılır. Kaynakta bütçe kavramı yoktur `[doğrulandı: belge 05 §2]`.

### 8.3 Geri çekilme ve yeniden deneme matrisi

| Hata sınıfı | Yeniden deneme | Gecikme | Not |
|---|---|---|---|
| Geçici ağ (reset, timeout) | 1 | 1 sn | |
| 429 | ≤ 3 | `Retry-After` veya 1/2/4 sn ± jitter | devre kesici sayacına girer |
| 5xx | 1 | 2 sn | |
| 4xx (404/410/403) | 0 | – | bulgudur |
| SSRF reddi | 0 | – | asla yeniden denenmez, **kayıt altına alınır** (§15) |
| Kural/kod istisnası | 0 | – | hata alarmı |
| LLM 429/5xx | ≤ 3 | üstel + jitter | sağlayıcı başlıklarına uy |
| LLM şema ihlali | 1 | – | düzeltme istemiyle tek deneme |

Worker düzeyinde yeniden deneme (kuyruk) ile istek düzeyinde yeniden deneme (HTTP) **birbirine katlanmaz**: yalnız bir katman yeniden dener (istek düzeyi), kuyruk düzeyi yalnız worker çökmesi içindir.

## 9. Katman C: LLM aşaması

### 9.1 Modüller (Faz 2)

| Modül | Çıktı | Genel skora girer mi | Girdi |
|---|---|---|---|
| `content_eeat` | danışma skoru (E-E-A-T bantları) + kanıtlı gözlemler | **Hayır** (D3) | çıkarılmış metin + yapısal alanlar |
| `ai_readiness_commentary` | AI arama hazırlığı yorumu, öneriler | Hayır | robots AI bot tablosu, `js_gap`, yapı |
| `synthesize` | `top_findings`, `quick_wins` metni, bulgu başına öneri metni | Hayır | bulgular + skorlar |

Kaynaktaki ajanların (`seo-content`, `seo-geo`) E-E-A-T ağırlıkları (Deneyim %20, Uzmanlık %25, Otorite %25, Güven %30) ve GEO boyutları (belge 05 raporu, 01 §7) rubrik başlangıcı olarak kullanılır; kaynak bunların "Google'ın ağırlıkları değil, iç model" olduğunu açıkça yazar `[doğrulandı: agents/seo-content.md]`, biz de raporda aynı notu taşırız.

### 9.2 Çağrı akışı

```
girdi kurucu ──▶ önbellek? ──evet──▶ cache hit (maliyet 0)
     │ hayır
     ▼
bütçe kontrolü ──aşıldı──▶ partial ("üretilemedi: bütçe")
     │
     ▼
BYOK/anahtar çöz ──▶ LLM çağrısı (sıcaklık 0, yapılandırılmış çıktı)
     │
     ▼
JSON Schema doğrula ──ihlal──▶ 1 düzeltme denemesi ──yine ihlal──▶ "üretilemedi"
     │
     ▼
KANIT DOĞRULAMA: her alıntı sayfa metninde birebir var mı? ──hayır──▶ gözlem reddedilir
     │
     ▼
yaz: advisory_scores, bulgular, llm_calls (maliyet, token, model, rubrik sürümü), llm_cache
```

### 9.3 Girdi güvenliği (prompt injection) `[K+B]`
- Model **ham HTML görmez**; yalnız çıkarılmış alanlar (başlık, `extracted_text`, JSON-LD özeti, yapı sayıları) `[K: trafilatura çıkarımı]`.
- Sayfa kaynaklı her string açıkça sınırlayıcı etiketler içinde verilir ve sistem prompt'u bunu "veri, talimat değil" diye tanımlar `[K: SKILL.md Security bölümü]`.
- Çıktı **yalnız şemaya uyan** alanlardan oluşur; serbest metin yalnız `recommendation`/`observation` alanlarında ve **sayfa metninden alıntıyla desteklenmeden** kabul edilmez (§9.2 kanıt doğrulaması).
- Model araç çağırma yeteneği taşımaz (ağ yok); yalnız metin üretir.
- Sayfadaki "ajana yönelik" talimat metni bir **bulgudur** (`prompt-injection-attempt`, Info) ve rapora yazılır, yürütülmez `[K: seo-audit Security]`.

### 9.4 Tekrarlanabilirlik `[B, belge 01 §4.1]`
Sıcaklık 0; rubrik bantları sabit sayısal eşleme; önbellek anahtarı `sha256(girdi_alanları) + rubrik_sürümü + model_id`; prompt şablonları sürümlüdür (`rule_versions`/`score_versions` ile aynı mekanizma). Model sürümü değişirse önbellek geçersiz olur, sonuç `model_id` ile işaretlenir.

### 9.5 Model ve maliyet `[B]`
- Varsayılan: küçük/hızlı model; derin mod (üst plan): daha güçlü model. Model adı **yapılandırmadır**, koda gömülmez.
- BYOK: kullanıcı anahtarı yalnız LLM worker'ında, bellekte çözülür, loga yazılmaz, istekten sonra bellekten atılır (belge 00 §3.4).
- Her çağrı `llm_calls`'a (tenant, audit, modül, model, token, maliyet, süre, cache_hit) ve `usage_ledger`'a yazılır; aylık kota ve denetim başına tavan buradan hesaplanır.

## 10. Soru-cevap hizmeti (L3) `[B]`

```
POST /v1/audits/{id}/qa  {question}
   │
   ▼
yetki + kota + token tavanı
   │
   ▼
Bağlam kurucu (DETERMİNİSTİK): soru → ilgili kategori/finding id'leri (anahtar sözcük + kategori eşleme)
   │                           bağlam = skorlar + seçilen bulgular (kırpılmış) + metodoloji notları
   ▼
LLM (araçsız, ağsız) ──▶ yanıt + atıflar [finding_id...]
   │
   ▼
SON KONTROL: her atıf gerçekten bağlamda var mı? atıfsız iddia → reddet/yeniden üret
   │
   ▼
qa_messages'a yaz (yanıt, atıf, token, maliyet)
```

- **Ağ yok, fetch yok:** Q&A yalnız kayıtlı rapordan yanıtlar (belge 00 §3.2). Bu hem SSRF yüzeyini hem maliyeti sınırlar.
- **Retrieval için vektör veritabanı gerekmez:** rapor yapılandırılmıştır (id, kategori, severity); basit filtre ve anahtar sözcük eşleme yeterlidir. Büyük raporlarda bağlam, severity ve konuya göre kırpılır.
- **Rapor dışı soru** (genel SEO sohbeti): kibar ret ("Bu raporda ölçülmedi" veya kapsam dışı).
- **Güvenilmeyen `evidence`:** talimat sayılmaz; bağlamda etiketli verilir.
- **Tavanlar:** denetim başına soru sayısı, soru başına bağlam ve yanıt token'ı, günlük kiracı kotası.
- **Önbellek:** aynı denetim ve aynı normalize soru için yanıt önbelleği.

## 11. Yeniden çalıştırma ve yeniden skorlama

### 11.1 Modül yeniden çalıştırma (kullanıcıya açık, belge 00 §3.2)
`POST /v1/audits/{id}/rerun {modules:[...]}` → **yeni** `audit` satırı, `parent_audit_id` dolu. Eskisi değişmez.

| Modül türü | Davranış | Maliyet |
|---|---|---|
| Katman A/B | **Yeniden fetch yapmadan**, ebeveynin saklanan `page_fetches` gövdeleri üzerinde yeniden çalışır (saklama süresi içinde); gövde silindiyse yeniden fetch | ucuz |
| Katman C | LLM kotasından düşer; girdi hash'i aynıysa önbellekten | kotalı |
| Fetch/render tabanlı | Taze fetch (kullanıcı "yeniden tara" derse) | nezaket sınırlarına tabi |

### 11.2 Yeniden skorlama (iç yetenek, kullanıcıya açık değil)
Kural/skor sürümü yükseldiğinde, eski denetimin **saklanan gövdeleri** üzerinde yeni sürümle yeniden hesap yapılabilir (yeni `audit`, `parent_audit_id`). Kalibrasyonda (belge 01 §13.2) ve regresyon testinde kullanılır. Eski rapor değişmez.

## 12. Zamanlanmış izleme (Faz 3) `[B]`

- **Zamanlayıcı** (`monitoring_schedules`): haftalık/günlük, kiracı planına bağlı; yalnız **doğrulanmış** siteler (belge 05 D11).
- Her çalıştırma **çekirdek örneklem** (sabit) + **keşif örneklemi** (dönen tohum) içerir (belge 00 §3.3).
- **Baseline** (`drift_baselines`): çekirdek sayfaların anlık görüntüsü; sonraki çalıştırmalar `drift_events` üretir (17 kural, belge 01 §10). Kaynaktaki SQLite şeması ve kural motoru portlanır `[K]`.
- Drift **skoru etkilemez**; ayrı uyarı akışıdır. Skor trendi yalnız aynı `score_version` içinde çizilir.
- Bildirim (e-posta/webhook) belge 06'te.

## 13. İlerleme olayları (SSE)

Control worker her aşama geçişinde Redis pub/sub'a olay yazar; API bunu SSE'ye çevirir. Olay: `{audit_id, stage, status, pages_fetched, pages_planned, message_key, ts}`. Olaylar DB'ye de yazılır (yeniden bağlanan istemci `Last-Event-ID` ile kaldığı yerden devam eder). Kullanıcı sayfayı kapatsa denetim sürer; SSE yalnız gözlem kanalıdır.

## 14. İptal, zaman aşımı ve hedefler

- **İptal:** `audits.cancel_requested` bayrağı; worker'lar her iş başlangıcında ve uzun işlerde periyodik olarak kontrol eder (işbirlikçi iptal). Uçuştaki HTTP istekleri sonuçlanıp atılır.
- **Aşama zaman aşımları:** fetch sayfa başına 45 sn (belge 05 §6.1), render 15 sn, LLM çağrısı 60 sn `[?]`, tüm denetim duvar saati ≤ 5 dk (belge 05 §10); süre dolunca `partial`.
- **Hedefler (SLO, ölçülecek `[?]`):**

| Mod | LLM'siz | LLM'li |
|---|---|---|
| Sayfa analizi | p95 < 20 sn | p95 < 60 sn |
| Site denetimi (50 sayfa) | p95 < 3 dk | p95 < 5 dk |

Bu sayılar tahmindir; Faz 1'de ölçülüp güncellenir.

## 15. Gözlemlenebilirlik ve kötüye kullanım

### 15.1 Günlük ve metrik
- **Yapılandırılmış günlük:** her satırda `audit_id`, `tenant_id`, `stage`, `shard`, `worker`, `request_id`. URL'ler günlükte **sorgu parametreleri maskelenmiş** yazılır (belge 06/04 gizlilik; kaynak da sitemap URL'lerindeki sır parametrelerini maskeler `[doğrulandı: sitemap_discovery._SECRET_PARAM]`).
- **Metrikler:** aşama süresi, kuyruk derinliği, fetch hata oranı (sınıfa göre), render hata oranı, LLM maliyeti/denetim, önbellek isabet oranı, partial/failed oranı, kural istisnası sayısı.
- **Alarmlar:** `score`/`report` aşamasında hata (kod hatası), kural istisnası artışı, LLM maliyet sapması, egress proxy ret oranı.

### 15.2 Dış istek kaydı (kötüye kullanım ve şikayet)
Her dış isteğin (`tenant_id`, `audit_id`, hedef host, zaman, durum) denetim kaydı tutulur. Amaç: bir site sahibi "bu bot bize saldırıyor" dediğinde kimin, ne zaman ne kadar istek yolladığını gösterebilmek ve gerekirse engellemek. **SSRF reddi** denemeleri ayrı olarak kaydedilir ve tekrarlayan kiracı otomatik kısıtlanır `[B]`.

### 15.3 Engelleme ve geri bildirim
Bot bilgi sayfası (D10) bir iletişim adresi ve **muafiyet listesi** sunar: site sahibi `robots.txt` ile veya doğrudan başvuruyla engel koyabilir; engel listesi `validate` aşamasında denetlenir.

## 16. Dağıtım ve ölçekleme (özet)

- Her worker türü ayrı bir konteyner imajı; Fetch/Render ayrı ağ ve hesapta (§3.1).
- Otomatik ölçekleme sinyali: kuyruk derinliği (`q_fetch`, `q_render`, `q_llm`).
- PostgreSQL bağlantı havuzu (worker sayısı × havuz boyutu ≤ sınır); okuma yükü (rapor görüntüleme) için okuma kopyası sonra `[?]`.
- Sıfır kesinti dağıtımı: worker'lar `SIGTERM`'de yeni iş almayı bırakıp süren işi bitirir; süren işler lease sayesinde başka worker'a geçebilir.
- Nesne depolama: HTML gövdeleri, raporlar, PDF; saklama süreleri belge 04'te.

## 17. Test stratejisi

| Katman | Yaklaşım |
|---|---|
| Kontroller/skor | Saf fonksiyon: golden fixture, property testleri (belge 01 §13); kaynak test paketi taşınır (belge 00 §4) |
| Durum makinesi | Her geçiş için birim test; **tekrar oynatma**: aynı olay dizisi → aynı son durum |
| Idempotency | Aynı aşama iki kez çalıştır → tek satır, aynı içerik |
| Çökme dayanıklılığı | Aşama ortasında worker'ı öldür → lease sonrası başka worker devralır, sonuç aynı |
| Fan-in | Eksik/geç/çift olaylarla yarış testleri; deadline'da kısmi finalize |
| Nezaket | Sahte zamanlayıcı ile semafor/token bucket; iki kiracı aynı host |
| Fetch/SSRF | Belge 05 §13 düşmanca girdiler; egress proxy'nin özel aralığı **gerçekten** reddettiği dağıtım testi |
| LLM | Kayıtlı yanıtlarla (VCR benzeri) sahte sağlayıcı; şema ihlali, kanıt doğrulama, bütçe aşımı, injection içerikli sayfa |
| Q&A | Atıfsız iddia reddi, rapor dışı soru reddi, bağlam kırpma |
| Yük | Eşzamanlı 100 denetim, tek hedef host: hedefin gördüğü istek hızı sınır altında mı |

## 18. Doğrulama matrisi (kaynak ↔ bu belge)

| İddia | Kontrol | Sonuç |
|---|---|---|
| Orkestrasyon LLM prompt'udur, kod değil | `skills/seo-audit/SKILL.md` adım 4 "Delegate to subagents (if available, otherwise run inline sequentially)" | ✅ |
| Koşullu tetikleme tablosu kaynakta var (local, maps, google, matomo, backlinks, cluster, sxo, drift, ecommerce) | `seo-audit/SKILL.md` adım 4 | ✅ |
| Partial→complete bulgu yazma deseni | `seo-audit/SKILL.md` "Error Handling" satırı (`maxTurns`) | ✅ |
| 5 Opus ajanı: cluster, content, drift, geo, sxo | `agents/*.md` `model:` alanları bu oturumda okundu | ✅ |
| Kaynakta eşzamanlılık havuzu/oran sınırı/retry yok | Belge 05 §14 doğrulaması | ✅ |
| E-E-A-T ağırlıkları "Google'ın değil, iç model" notu | `agents/seo-content.md` | ✅ |
| Sitemap URL'lerinde sır parametresi maskeleme | `sitemap_discovery._SECRET_PARAM` | ✅ |
| `page_checks.run_checks` `findings/not_checked/summary` döndürür | `page_checks.py` | ✅ |
| Prompt injection kuralı ve "agent-addressed text is a finding" | `seo-audit/SKILL.md` Security | ✅ |

**Doğrulanmadı:** Arq'un tüm gereksinimlerimizi (gecikmeli iş, lease, yeniden deneme semantiği, iş önceliği) karşıladığı; Redis semafor/token bucket desenlerinin çökme senaryolarında davranışı; Playwright render'ın bellek/eşzamanlılık değerleri. Hepsi **Faz 0 prototipinde** doğrulanacak.

## 19. Açık kararlar

| # | Karar | Öneri | Not |
|---|---|---|---|
| D13 | Kuyruk teknolojisi | **Arq** (asyncio, Redis) | Alternatif: Celery, Dramatiq. Faz 0 prototipi: gecikmeli iş, lease, öncelik, çökme davranışı |
| D14 | LLM sağlayıcı soyutlaması | İlk sürümde **tek sağlayıcı** (Anthropic), ince bir arayüz | BYOK de aynı sağlayıcının anahtarı |
| D15 | SLO hedefleri | §14 tablosu | Faz 1'de ölçülüp güncellenir |
| D16 | Kötüye kullanım politikası (eşikler, otomatik kısıt, muafiyet süreci) | §15 | Hukuki/ürün onayı |
| D12 | Render barındırma (belge 05'deki karar) | Kendi izole worker + egress firewall | Yönetilen tarayıcı servisleri güvenlik/maliyet açısından sonra değerlendirilir |
| D8, D10, D11 | (belge 05'den) | Giriş URL'i istisnası; `SEOAnalyzerBot` + bilgi sayfası; doğrulanmamış 25 / doğrulanmış 50-200 | Önerilerle ilerlenir, onay bekler |

## 20. Sonraki belgeler

| Belge | Konu | Bu belgeden devraldığı |
|---|---|---|
| [`03-rubrik-and-prompts.md`](03-rubrik-and-prompts.md) | Katman C modülleri: rubrik, prompt, doğrulayıcı | §9 LLM akışı, §10 Q&A, §11 yeniden çalıştırma |
| [`04-data-model.md`](04-data-model.md) | Tablolar, DDL, RLS, saklama | `audit_stages`, lease, `llm_calls`, `usage_ledger`, `qa_*`, `budget` |
| [`05-system-design.md`](05-system-design.md) | Fetch, render, SSRF, örneklem | §3.2 sonuç yazma yolu, §8 bütçe ve nezaket |
| [`06-io-schemas.md`](06-io-schemas.md) | API, rapor JSON şeması | SSE olayları, Q&A ve yeniden çalıştırma uç noktaları, `partial` gösterimi |
| [`08-file-structure.md`](08-file-structure.md) | Dosya yapısı | Worker türleri, Dockerfile'lar, import sınırları |
| [`09-implementation-roadmap.md`](09-implementation-roadmap.md) | Faz faz uygulama | Aşama ve worker sıralaması, Faz 0 prototipleri (P2, P3, P4) |
| [`10-decision-log.md`](10-decision-log.md) | Karar günlüğü | D12-D16 ve ilgili kararlar |
