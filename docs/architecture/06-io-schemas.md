# 06. Girdi/Çıktı Şemaları: API ve Rapor

> Durum: **Taslak v0.1** · Önceki belgeler: [`01-evaluation-system.md`](01-evaluation-system.md) (v0.2), [`05-system-design.md`](05-system-design.md) (v0.2), [`00-capability-parity.md`](00-capability-parity.md) (v0.2)
> İşaretler: `[K]` kaynak projeden alındı · `[B]` bizim kararımız · `[?]` açık karar · `[doğrulandı]` kaynak kodla kontrol edildi
> Yığın (sözleşme): Python ≥ 3.11, FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL, Redis, Arq worker. Kütüphane seçimleri `[B]` önerisidir. Arayüz teknolojisi açık karardır (IO1).
> Not: Veri modeli (tablolar, saklama süreleri) belge 04'te, iş kuyruğu ve worker akışı belge 02'te ele alınır. Bu belge **dışarıdan görünen yüzeyi** tanımlar: API, `audit.json` şeması ve rapor arayüzü.

---

## 1. Amaç ve ilkeler

Kullanıcı bir URL girer, ilerlemeyi izler, raporu okur, geçmişle karşılaştırır, rapora soru sorar ve modülleri yeniden çalıştırır. Bu belge o deneyimin sözleşmesidir.

| # | İlke | Gerekçe |
|---|---|---|
| R1 | **Tek doğruluk kaynağı `audit.json`.** HTML, PDF, API yanıtları ve Q&A bağlamı bu dosyadan türer. `[K: ayrık analiz/sunum]` | kaynak proje da bulguları `audit-data.json`'a yazıp raporu ayrı script ile üretir; ama şema dosyası yoktur, ölü alanlar birikmiştir `[doğrulandı]` |
| R2 | **Şema koddur.** Pydantic modelleri yazılır, JSON Schema bunlardan üretilir, her rapor yayından önce doğrulanır. `[B]` | Kaynakta şema yalnız SKILL.md'deki örnek JSON'dur |
| R3 | **Skor ve bulgu belge 01 sözleşmesine birebir uyar.** Rapor katmanı skoru değiştirmez, yeniden hesaplamaz, yalnız gösterir. | Skor tek yerde (scorer) hesaplanır |
| R4 | **Ölçülmeyen şey gösterilir ama puanlanmaz.** "Ölçülmedi" birinci sınıf bir görsel durumdur. `[K+B]` | Belge 01 P2 |
| R5 | **Sayfadan gelen her string güvenilmezdir.** Tüm çıktı yüzeylerinde (HTML, PDF, JSON, Q&A) o şekilde ele alınır. `[K]` | Belge 01 P7; XSS ve prompt injection |
| R6 | **Renk tek başına anlam taşımaz.** Şiddet ve skor bandı her zaman ikon ve metinle de belirtilir. `[B]` | Erişilebilirlik; kaynak raporda 5 şiddet aynı amber çıkıyor `[doğrulandı]` |
| R7 | **Değişmez rapor.** Tamamlanan bir `audit` satırı ve `audit.json` değiştirilmez; yeniden çalıştırma yeni satırdır. `[B]` | Tekrarlanabilirlik, trend güvenilirliği |
| R8 | **Zarif bozulma.** Render, PSI veya LLM başarısız olsa bile rapor çıkar; eksik kısım `not_checked`/`limitations` ile söylenir. `[K+B]` | Belge 01 P8; kaynakta HTML, PDF bağımlılığı olmadan da üretilir |

## 2. Kullanıcı akışı

```
 ┌─────────┐   ┌───────────┐   ┌──────────┐   ┌─────────┐   ┌───────────┐   ┌────────────┐
 │ 1. URL  │──▶│ 2. İlerle │──▶│ 3. Rapor │──▶│ 4. Geçm.│   │ 5. Soru   │   │ 6. Yeniden │
 │   gir   │   │   me      │   │  (HTML)  │   │ ve trend│   │   sor     │   │   çalıştır │
 └─────────┘   └───────────┘   └──────────┘   └─────────┘   └───────────┘   └────────────┘
   mod seç       SSE olayları     skor+bulgu     site başına    yalnız rapor   modül seç,
   (site|page)   stage/progress   aksiyon planı  çekirdek örnek.  bağlamı       yeni audit
   doğrula       iptal edilebilir paylaş/indir   trend          atıflı cevap   (parent_audit_id)
```

| Adım | Kullanıcı ne görür | Sistem ne yapar |
|---|---|---|
| 1. Giriş | URL alanı, mod (Site denetimi / Sayfa analizi), dil (TR/EN). Doğrulanmamış site ise sayfa tavanı bilgisi | `POST /v1/audits`; giriş normalizasyonu ve SSRF ön kontrolü (belge 05 §4-5) eşzamanlı yapılır, reddedilirse **202 değil 422** döner |
| 2. İlerleme | Aşama çubuğu (Doğrulama → Çekme → Keşif → Ölçüm → Skor → Yorum → Rapor), çekilen sayfa sayacı, "İptal" | `GET .../events` (SSE). Kısmi sonuç hazırsa "Şimdilik gör" düğmesi (`status=partial`) |
| 3. Rapor | Skor kartı, kapsam, güven, kapı bandı (varsa), kategoriler, bulgular, aksiyon planı, danışma bölümü, metodoloji | `audit.json` → HTML (§5) |
| 4. Geçmiş | Site başına denetim listesi ve **çekirdek örneklem** trend grafiği; `score_version` değiştiyse kopuk çizgi | `GET /v1/sites/{id}/history` |
| 5. Soru sor | Rapor üstünde soru kutusu; cevaplar bulgu ve URL atıflı; rapor dışı soru nazikçe reddedilir | `POST .../qa` (§3.3) |
| 6. Yeniden çalıştır | Modül seçimi (örn. yalnız Teknik + Schema); Katman C modülleri için kota uyarısı | `POST .../rerun` → yeni audit, eskisi dokunulmaz |

## 3. REST API

### 3.1 Genel kurallar

| Konu | Karar |
|---|---|
| Taban | `https://api.<alan-adı>/v1` (alan adı belirlenecek, belge 05 D10) |
| Biçim | `application/json; charset=utf-8`. Hata: `application/problem+json` (RFC 9457) `[B]` |
| Kimlik (minimal) | Programatik: `Authorization: Bearer <api-anahtarı>` (anahtar yalnız özet/hash olarak saklanır, kapsam: `read`, `write`). Web arayüzü: `HttpOnly; Secure; SameSite=Lax` oturum çerezi + durum değiştiren isteklerde CSRF belirteci. Kimlik sağlayıcısı ve faturalama bu belgenin **kapsamı dışıdır** |
| Kiracı izolasyonu | Her kaynak `tenant_id` ile kapsanır; erişim ihlali **404** döner (varlık sızdırmaz) |
| Kimlikler | Dışa açık kimlikler öneklidir ve tahmin edilemez: `aud_…`, `site_…`, `shr_…` (≥128 bit rastgelelik; sıralı ULID tek başına yeterli sayılmaz) `[B]` |
| Zaman | RFC 3339, UTC (`2026-11-13T10:00:00Z`) |
| Sürümleme | URL'de ana sürüm (`/v1`). Alan eklemek kırıcı değildir; kaldırma/anlam değişimi `/v2`. Kullanımdan kaldırma `Deprecation` ve `Sunset` başlıklarıyla duyurulur. `audit.json` kendi `schema_version` (semver) değerini taşır; eski raporlar okunurken yükseltme fonksiyonundan geçer, yeniden yazılmaz |
| Sayfalama | İmleç tabanlı: `?limit=50&cursor=…` → `{ "data": [...], "next_cursor": "…"|null, "has_more": bool }`. Varsayılan 50, en çok 200 |
| Oran sınırı | `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset` ve aşımda `429` + `Retry-After`. `[doğrulandı değil]` IETF başlık taslağının güncel adları uygulama öncesi kontrol edilmeli |
| İdempotensi | `Idempotency-Key` başlığı: `POST /audits`, `/rerun`, `/qa`. Aynı anahtar + aynı gövde → ilk yanıt (24 saat); aynı anahtar + farklı gövde → `422 idempotency-key-reuse`; ilk istek sürüyorsa → `409 request-in-flight` |
| Çift denetim | Aynı kiracı için aynı normalize hedef ve mod ile **sürmekte olan** denetim varsa `409 audit-in-progress` + mevcut denetimin bağlantısı döner (kötüye kullanım ve maliyet önlemi, belge 05 §10) |
| CORS | Varsayılan kapalı; yalnız belirlenmiş arayüz kökenine izin |
| İçerik güvenliği | Tüm JSON yanıtlarda `X-Content-Type-Options: nosniff`. `evidence` alanı sayfa kaynaklıdır; **tüketici bunu işaretleme değil metin olarak göstermelidir** (belge, API dokümantasyonuna yazılır) |

### 3.2 Uç noktalar

| Yöntem | Yol | Amaç | Not |
|---|---|---|---|
| **Denetimler** | | | |
| POST | `/audits` | Denetim başlat | 202 Accepted + `Location`. İdempotent |
| GET | `/audits` | Liste (filtre: `site_id`, `status`, `mode`, `created_after`) | İmleç sayfalama |
| GET | `/audits/{id}` | Durum, aşama, ilerleme, skor özeti | Hafif; rapor gövdesi yok |
| GET | `/audits/{id}/report` | Tam `audit.json` | `status ∈ {partial, completed}`; yoksa `409 audit-not-ready` |
| GET | `/audits/{id}/findings` | Bulgu listesi | Filtre: `severity`, `category`, `layer`, `scope`, `check_id`, `url`; sıralama: `severity`, `priority` |
| GET | `/audits/{id}/pages` | Örneklenen sayfalar (`role`: core/exploration) | |
| GET | `/audits/{id}/events` | İlerleme akışı (SSE) | `Last-Event-ID` ile devam |
| POST | `/audits/{id}/cancel` | İptal | Kısmi rapor üretilir (`canceled`) |
| POST | `/audits/{id}/rerun` | Modül yeniden çalıştır | Yeni denetim, `parent_audit_id` |
| POST | `/audits/{id}/qa` | Rapora soru | Yalnız kayıtlı rapordan cevap |
| GET | `/audits/{id}/qa` | Soru-cevap geçmişi | |
| POST | `/audits/{id}/shares` | Paylaşım bağlantısı oluştur | İmzalı, süreli |
| DELETE | `/shares/{share_id}` | Bağlantıyı iptal et | |
| GET | `/audits/{id}/report.pdf` | PDF | **Faz 3** (§7.3) |
| **Siteler** | | | |
| GET | `/sites` · `/sites/{id}` | Site listesi/ayrıntı (doğrulama düzeyi, son denetim) | |
| GET | `/sites/{id}/history` | Trend (çekirdek örneklem skorları) | `score_version` kopuşları işaretli |
| POST | `/sites/{id}/verification` | Sahiplik doğrulamayı başlat (`dns_txt`/`meta_tag`/`file`) | Meydan okuma (challenge) döner |
| POST | `/sites/{id}/verification/check` | Doğrulamayı dene | |
| DELETE | `/sites/{id}/verification` | Doğrulamayı kaldır | Kota düzeyi düşer |
| **Hesap** | | | |
| PUT | `/account/llm-key` | BYOK anahtarı ayarla/değiştir | Yalnız Katman C; yanıt anahtarı **asla** döndürmez |
| GET | `/account/llm-key` | Maskeli durum (`last4`, `valid`, `set_at`) | |
| DELETE | `/account/llm-key` | Sil | |
| GET | `/usage` | Dönem kullanımı ve limitler | |
| **Meta** | | | |
| GET | `/rules` | Kural kaydı (id, severity, kategori, katman, `heuristic`, `message_key`) | Şeffaflık; açık karar IO8 |
| GET | `/health` | Canlılık | Kimlik gerekmez |

Doğrulama ve doğrulanmamış tavan kuralı `[B, belge 05 D11]`: `tier=unverified` iken `options.max_pages` 25'e kırpılır ve yanıt `limits.applied` içinde bunu söyler. İstek tavanı aşarsa **hata değil kırpma**, ama açıkça raporlanır.

### 3.3 İstek ve yanıt örnekleri

**Denetim başlat**

```http
POST /v1/audits
Authorization: Bearer sk_live_…
Idempotency-Key: 7f6c1f0e-3c44-4c0a-9f77-2b6a8c1d5e10
Content-Type: application/json

{
  "url": "example.com",
  "mode": "site",
  "locale": "tr",
  "options": {
    "max_pages": 50,
    "core_urls": ["https://example.com/fiyatlar"],
    "layers": { "A": true, "B": true, "C": true },
    "llm": { "use_byok": false }
  }
}
```

```http
HTTP/1.1 202 Accepted
Location: /v1/audits/aud_01HX9Q7B2K3M4N5P6R7S8T9V0W
Content-Type: application/json

{
  "id": "aud_01HX9Q7B2K3M4N5P6R7S8T9V0W",
  "mode": "site",
  "status": "queued",
  "stage": "validate",
  "requested_url": "example.com",
  "normalized_url": "https://example.com/",
  "site_id": "site_9d3a1c2e5b7f40d8",
  "tier": "unverified",
  "locale": "tr",
  "limits": {
    "requested_max_pages": 50,
    "applied_max_pages": 25,
    "reason": "tier_unverified"
  },
  "created_at": "2026-11-13T10:00:00Z",
  "links": {
    "self": "/v1/audits/aud_01HX9Q7B2K3M4N5P6R7S8T9V0W",
    "events": "/v1/audits/aud_01HX9Q7B2K3M4N5P6R7S8T9V0W/events",
    "report": "/v1/audits/aud_01HX9Q7B2K3M4N5P6R7S8T9V0W/report"
  }
}
```

**Durum**

```json
{
  "id": "aud_01HX9Q7B2K3M4N5P6R7S8T9V0W",
  "mode": "site",
  "status": "running",
  "stage": "fetch_pages",
  "progress": { "pages_planned": 25, "pages_fetched": 11, "pages_rendered": 1 },
  "started_at": "2026-11-13T10:00:02Z",
  "partial_available": false,
  "scores_preview": null
}
```

**İlerleme akışı (SSE)**: sunucu `id:` ile olay numarası verir, istemci `Last-Event-ID` ile kaldığı yerden devam eder; 15 sn'de bir `heartbeat`.

```
id: 14
event: stage
data: {"stage":"fetch_pages","status":"running","at":"2026-11-13T10:00:21Z"}

id: 15
event: progress
data: {"pages_planned":25,"pages_fetched":12,"pages_rendered":1}

id: 31
event: partial
data: {"available":true,"categories_measured":["technical","onpage","schema","images"]}

id: 40
event: completed
data: {"status":"completed","report":"/v1/audits/aud_01HX9Q7B2K3M4N5P6R7S8T9V0W/report"}
```

Olay türleri: `stage`, `progress`, `partial`, `completed`, `failed`, `canceled`, `heartbeat`. Aşama adları sözleşmedeki `stage` enum'udur (`validate … report`).

**Bulgu listesi**

```http
GET /v1/audits/aud_…/findings?severity=Critical,High&category=technical&limit=2
```

```json
{
  "data": [
    {
      "id": "fnd_0001",
      "check_id": "canonical-points-elsewhere",
      "category": "technical",
      "layer": "A",
      "severity": "High",
      "scope": "page",
      "url": "https://example.com/a",
      "message_key": "check.canonical-points-elsewhere",
      "message": "Canonical başka bir URL'yi işaret ediyor, bu sayfa o URL'nin indekslenmesini istiyor. Bunun bilinçli olduğunu doğrulayın.",
      "evidence": { "value": "https://example.com/b", "truncated": false },
      "affected": { "count": 1, "share_of_sampled_pages": 0.04, "examples": ["https://example.com/a"] },
      "recommendation_ids": ["rec_0001"]
    }
  ],
  "next_cursor": "eyJvIjoyfQ",
  "has_more": true
}
```

**Soru sor (rapor üstünde)**

```http
POST /v1/audits/aud_…/qa
Idempotency-Key: 0a1b…
Content-Type: application/json

{ "question": "Önce hangi üç şeyi düzeltmeliyim?", "locale": "tr" }
```

```json
{
  "id": "qa_01HX…",
  "answer": "Rapora göre önce şunlar: 1) Ana sayfadaki canonical sorunu (fnd_0001)…",
  "citations": [
    { "finding_id": "fnd_0001", "url": "https://example.com/a" },
    { "finding_id": "fnd_0007", "url": null }
  ],
  "refused": false,
  "refusal_reason": null,
  "usage": { "input_tokens": 3120, "output_tokens": 240, "byok": false }
}
```

Reddedilen soru: `"refused": true`, `"refusal_reason": "out_of_scope" | "not_measured" | "quota"`; `answer` kısa ve sabit bir metindir ("Bu raporda ölçülmedi" gibi). Kurallar `[B, belge 00 §3.2]`:
- Bağlam yalnız `audit.json`'dan kurulan bir alt kümedir; **araç çağrısı yok, fetch yok**.
- Cevaptaki her iddia bir `finding_id` veya kategori skoruna atıf yapmalıdır; atıfsız cevap `refused` olarak işaretlenir.
- Cevaptaki her atıf raporda gerçekten var olmalıdır (sunucu doğrular, yoksa cevap düşürülür).
- Soru ≤ 500 karakter; denetim başına soru ve token tavanı plana bağlıdır (IO5).
- `evidence` ve sayfa kaynaklı her metin istemde **veri bloğu olarak çevrelenir** ve talimat sayılmaz.
- Çıktı kısıtlı bir işaretlemeyle sınırlanır: ham HTML, görüntü ve harici bağlantı **yok** (veri sızdırma yolu olan işaretlemeli görüntüler engellenir).

**Yeniden çalıştırma**

```json
{
  "modules": ["technical", "schema", "advisory"],
  "refresh": true
}
```

```json
{
  "id": "aud_01HX9T…",
  "parent_audit_id": "aud_01HX9Q7B2K3M4N5P6R7S8T9V0W",
  "status": "queued",
  "rerun": { "modules": ["technical", "schema", "advisory"], "refresh": true, "llm_quota_cost_estimate": { "calls": 1 } }
}
```

Modül kimlikleri: `technical`, `onpage`, `content`, `schema`, `performance`, `ai_readiness`, `images` (kategori modülleri, Katman A/B), `advisory` (E-E-A-T/SXO), `synthesis` (öneriler ve aksiyon planı metni). Kurallar `[B]`:
- `refresh: true`: Katman A/B modülleri siteyi **yeniden çeker** (kullanıcı düzeltme yaptı mı görmek için). Varsayılan budur.
- `advisory` ve `synthesis` (Katman C) **hiç fetch yapmaz**; üst denetimin saklanmış çıkarılmış alanlarını kullanır (belge 00 §3.2). Bu, **çıkarılmış alanların saklanmasını** gerektirir; saklama süresi belge 04'te karara bağlanır (IO4). Süre dolmuşsa `409 snapshot-expired`.
- Katman C içeren her yeniden çalıştırma, kullanıcı kotasından (veya BYOK ise anahtarından) düşer; `llm_quota_cost_estimate` istek yanıtında önceden bildirilir.
- Yeni denetim ancak **seçilmeyen modüllerin sonuçlarını üst denetimden devralırsa** tam bir rapordur. Devralınan bölümler raporda `inherited_from` ile işaretlenir, çünkü farklı zamanlarda ölçülmüşlerdir.

**Paylaşım bağlantısı**

```json
{ "expires_in_days": 7, "hide_evidence": false }
```

```json
{
  "id": "shr_5c1e…",
  "url": "https://app.<alan-adı>/r/Zk3Qm9…",
  "expires_at": "2026-11-20T10:00:00Z",
  "hide_evidence": false
}
```

**BYOK**

```http
PUT /v1/account/llm-key
{ "provider": "anthropic", "api_key": "sk-ant-…" }
```

```json
{ "provider": "anthropic", "last4": "…a9Qx", "valid": true, "set_at": "2026-11-13T10:00:00Z" }
```

Anahtar **hiçbir yanıtta, log'da veya hata mesajında yer almaz**; yalnız `last4` ve geçerlilik. Kaydetme sırasında en ucuz doğrulama çağrısıyla sınanır; geçersizse `422 llm-key-invalid`. Yalnız Katman C tarafından kullanılır, Katman A hiçbir zaman kullanıcı anahtarına dayanmaz `[B, belge 00 §3.4]`.

**Kullanım**

```json
{
  "period": { "start": "2026-11-01", "end": "2026-11-30" },
  "audits":  { "used": 12, "limit": 30 },
  "pages":   { "used": 410, "limit": 1500 },
  "llm":     { "tokens_used": 210000, "tokens_limit": 500000, "byok_enabled": false },
  "qa":      { "used": 18, "limit": 100 }
}
```

**Site doğrulama**

```json
{
  "method": "dns_txt",
  "challenge": { "record": "_seoanalyzer-verify.example.com", "type": "TXT", "value": "sav=2f9c1a…" },
  "expires_at": "2026-11-20T10:00:00Z"
}
```

### 3.4 Denetim durum makinesi

```
queued ──▶ running ──▶ completed
   │          │  ╲
   │          │   ╲──▶ partial   (bütçe/süre doldu veya kullanıcı "şimdilik gör"; rapor kısmi)
   │          ╲──────▶ failed    (hedef reddedildi/erişilemez; rapor yok, hata raporu var)
   ╰──────────────────▶ canceled (kullanıcı iptali; kısmi rapor varsa saklanır)
```

| Durum | Anlam | `report` |
|---|---|---|
| `queued` | Kuyrukta | Yok |
| `running` | Aşama `stage` alanındadır | Yok (`partial_available` olabilir) |
| `partial` | Elde edilenle üretilmiş **geçerli** rapor; `limitations` içinde nedeni var; kapsam düşer | Var, `status:"partial"` |
| `completed` | Tüm planlanan aşamalar bitti | Var |
| `failed` | Skor üretilemedi (`target-rejected`, `unreachable`, belge 05 §12) | Hata raporu (`audit.json`, skorsuz) |
| `canceled` | Kullanıcı iptal etti | Varsa kısmi |

`partial` bir hata değildir: **belge 01 §8.4** gereği kapsam %60'ın altına düşerse sayı yerine "Yetersiz veri" gösterilir, ama rapor yine de bulguları sunar.

### 3.5 Hata modeli (RFC 9457)

```json
{
  "type": "https://api.<alan-adı>/problems/target-rejected",
  "title": "Hedef reddedildi",
  "status": 422,
  "detail": "Bu adres genel internetten erişilebilir bir site değil.",
  "instance": "/v1/audits",
  "code": "target-rejected",
  "trace_id": "01HX9Q…",
  "errors": [{ "field": "url", "reason": "private_address" }]
}
```

| `code` | HTTP | Ne zaman |
|---|---|---|
| `validation-error` | 422 | İstek şeması hatalı |
| `target-rejected` | 422 | SSRF politikası veya geçersiz URL (belge 05 §5). `detail` ayrıntı sızdırmaz (hangi iç adres, hangi kural bilgisi verilmez) `[B]` |
| `unauthorized` | 401 | Kimlik yok/geçersiz |
| `forbidden` | 403 | Kapsam yetersiz |
| `verification-required` | 403 | Doğrulanmamış kullanıcı tavanı aşan özellik istedi |
| `not-found` | 404 | Yok **veya** başka kiracıya ait |
| `audit-not-ready` | 409 | Rapor henüz yok |
| `audit-in-progress` | 409 | Aynı hedef için denetim sürüyor |
| `request-in-flight` | 409 | Aynı `Idempotency-Key` ile istek sürüyor |
| `idempotency-key-reuse` | 422 | Aynı anahtar farklı gövdeyle kullanıldı |
| `snapshot-expired` | 409 | Yeniden çalıştırma için saklanan veri silinmiş |
| `llm-key-invalid` | 422 | BYOK anahtarı doğrulanamadı |
| `quota-exceeded` | 429 | Plan kotası doldu (`Retry-After` yok, `quota` alanı var) |
| `rate-limited` | 429 | Oran sınırı (`Retry-After` var) |
| `report-invalid` | 500 | Rapor kalite kapısı başarısız (§8); denetim `partial` kalır, içeride alarm |
| `internal-error` | 500 | Beklenmeyen |

## 4. Rapor JSON şeması (`audit.json`, nihai)

### 4.1 Üst düzey yapı

| Alan | Tip | Açıklama |
|---|---|---|
| `schema_version` | string (semver) | Rapor şeması sürümü, örn. `1.0.0` |
| `audit` | object | Kimlik ve yaşam döngüsü |
| `versions` | object | `score_version`, `rule_version`, `rubric_version`, `engine_version` |
| `target` | object | Hedef, iş tipi, dil |
| `crawl` | object | Örneklem ve **sayfa kapsamı** |
| `scores` | object | Genel skor, kategori skorları, kapı, güven |
| `trend` | object \| null | Çekirdek örneklem karşılaştırması |
| `advisory` | object \| null | LLM danışma skorları (E-E-A-T, SXO); **genel skora girmez** |
| `findings[]` | array | Tespit edilen sorunlar |
| `not_checked[]` | array | Ölçülemeyen kontroller ve gerekçeleri |
| `recommendations[]` | array | Öneriler (Katman C üretir, varsayılanlar kural kaydından) |
| `action_plan` | object | 4 fazlı plan |
| `pages[]` | array | Sayfa özetleri |
| `site_facts` | object | Site düzeyi olgular (robots, sitemap, TLS özeti) |
| `data_sources[]` | array | Veri kaynakları ve durumları |
| `limitations[]` | array | Sınırlamalar (kodlu) |
| `usage` | object | İstek, bayt, LLM kullanımı (paylaşılan görünümde gizlenir) |
| `quality` | object | Rapor kalite kapısı sonucu (§8) |
| `exports` | object | Üretilen çıktılar (`html`, `pdf`) |

**İsimlendirme uyarısı:** "kapsam" iki ayrı şeyi ifade eder ve alan adları bilerek ayrıdır:

| Alan | Anlam | Tanım |
|---|---|---|
| `scores.coverage_pct` | **Kategori kapsamı** | Ölçülen kategorilerin ağırlık toplamı ÷ uygulanabilir ağırlık toplamı × 100 (belge 01 §8.2) |
| `crawl.coverage` | **Sayfa kapsamı** | `pages_fetched` ÷ `pages_planned` ve keşfedilen/örneklenen oranı (belge 05 §9.4) |

Site modunda "uygulanabilir ağırlık" 7 kategorinin toplamıdır (=100). **Sayfa modunda** `performance` ve `ai_readiness` yalnız veri varsa listelenir (belge 01 §9); bu durumda uygulanabilir ağırlık, listelenen kategorilerin toplamıdır. Bu, belge 01'in kapsam tanımının sayfa moduna doğal genişlemesidir.

### 4.2 `audit`, `versions`, `target`

| Alan | Tip | Not |
|---|---|---|
| `audit.id` | string | `aud_…` |
| `audit.parent_audit_id` | string \| null | Yeniden çalıştırmada üst denetim |
| `audit.mode` | `site`\|`page` | |
| `audit.status` | `queued`\|`running`\|`partial`\|`completed`\|`failed`\|`canceled` | Rapor ancak `partial`/`completed`/`failed`'de vardır |
| `audit.tier` | `unverified`\|`verified` | Denetim anındaki düzey |
| `audit.locale` | `tr`\|`en` | Rapor dili |
| `audit.requested_url`, `audit.final_url` | string | Girilen ve redirect sonrası |
| `audit.site_id` | string | |
| `audit.started_at`, `audit.finished_at` | RFC 3339 | |
| `audit.rerun` | object \| null | `{modules[], refresh, inherited_modules[]}` |
| `versions.score_version` | string | Belge 01 P5 |
| `versions.rule_version` | string | Kural kaydı sürümü |
| `versions.rubric_version` | string \| null | Katman C rubrik sürümü |
| `versions.engine_version` | string | Uygulama sürümü |
| `target.origin`, `target.scope_hosts[]` | string | Belge 05 §4 site kapsamı |
| `target.business_type` | `{value, confidence, signals[], alternatives[]}` | `saas|local|ecommerce|publisher|agency|other`; ilk sürümde yalnız **etiket** (D4) |
| `target.language` | `{code, supported, detected_from}` | `supported=false` → dile bağlı kontroller kapalı (belge 01 §4.0) |

### 4.3 `crawl`

| Alan | Tip | Not |
|---|---|---|
| `crawl.limits` | `{max_pages_requested, max_pages_applied, reason}` | |
| `crawl.coverage` | `{pages_discovered, pages_planned, pages_fetched, pages_rendered, skipped{robots,error,out_of_scope}}` | Belge 05 §9.4 |
| `crawl.templates[]` | `{key, discovered, sampled}` | Şablon dağılımı |
| `crawl.sample_seed` | string | Tekrarlanabilirlik |
| `pages[].role` | `core`\|`exploration` | Çekirdek/keşif (belge 00 §3.3) |

### 4.4 `scores`

```
scores
├── kind: "health" | "page_card"
├── overall
│   ├── value: number | null          # kapsam < 60 ise null
│   ├── display: "number" | "insufficient_data"
│   ├── raw_value: number | null      # kapıdan önceki ham skor (kapı bandı için)
│   ├── coverage_pct: number          # kategori kapsamı
│   ├── confidence: "high" | "medium" | "low"
│   └── gate: null | { id, cap, finding_id, url, message_key }
└── categories[]
    ├── id: technical|onpage|content|schema|performance|ai_readiness|images
    ├── weight_default, weight_effective   # ölçülmeyen yeniden dağıtımdan sonra
    ├── status: "measured" | "partial" | "not_measured"
    ├── score: number | null               # not_measured ise null
    ├── confidence
    ├── checks_total, checks_run, checks_failed
    ├── passed_check_ids[]
    ├── penalties[] { finding_id, severity, points }
    ├── not_measured_reason: null | reason_code   # belge 05 §12 kodları
    └── finding_ids[]
```

Kurallar `[B]`:
- `scores.kind = "page_card"` iken yalnız sayfa modunda uygulanabilir kategoriler listelenir.
- `overall.value` **hiçbir zaman** `advisory` değerlerinden etkilenmez (§4.6).
- `overall.gate` doluysa `value = min(raw_value, cap)` olmalıdır (doğrulayıcı kontrol eder, §8).
- Kapsam %60'ın altındaysa `value=null` ve `display="insufficient_data"`; **dahili ham değer API'de gösterilmez**, yalnız saklanır.

### 4.5 `findings[]`, `not_checked[]`

| Alan | Tip | Not |
|---|---|---|
| `id` | string | Örnek kimliği, `fnd_…` |
| `check_id` | string | Kararlı kural kimliği `[K: page_checks id modeli]` |
| `rule_version` | string | |
| `category` | enum | 7 kategori |
| `layer` | `A`\|`B`\|`C` | |
| `severity` | `Critical`\|`High`\|`Medium`\|`Low`\|`Info` | Tek sözlük; kaynakta üç ayrı sözlük vardı `[doğrulandı: 08 §2.4]` |
| `severity_original`, `severity_reason` | string \| null | Bağlamla değiştiyse (belge 01 §7.3) |
| `scope` | `page`\|`site` | |
| `url` | string \| null | Sayfa kapsamlıysa |
| `message_key` + `params` | string + object | Kanonik, çevrilebilir metin anahtarı |
| `message` | string | Rapor dilinde **üretim anında çözülmüş kopya** (kolaylık; kanonik olan `message_key`) |
| `heuristic` | bool | `true` ise "arama motoru kuralı değil" notu gösterilir `[K]` |
| `evidence` | `{value, truncated}` | ≤ 200 karakter, kontrol/bidi karakterleri temizlenmiş `[K: page_checks._trim]`; **güvenilmez** |
| `count` | int \| null | Sayfa içi sayım |
| `affected` | `{count, share_of_sampled_pages, examples[≤5]}` | Site düzeyi bulgular için |
| `confidence` | enum | |
| `references[]` | string[] | Birincil kaynak URL'leri |
| `recommendation_ids[]` | string[] | |
| `inherited_from` | string \| null | Yeniden çalıştırmada devralındıysa |

`not_checked[]`: `{check_id, scope, url?, reason_code}` (`reason_code` belge 05 §12 kodlarından). `not_checked` hiçbir zaman "geçti" sayılmaz ve skor/bulgu sayısına girmez.

**Katman C bulguları** `[B]`: `layer="C"` bulgular **en fazla `High`** olabilir, **kapıyı tetikleyemez** ve ceza hesabına girmez; yalnız bilgi ve öneri taşırlar (kaynakta bunun karşılığı, "üçüncü taraf/varsayım kaynaklı bulgu Critical olamaz" önerisiydi `[08 §15.6]`).

### 4.6 `advisory`, `trend`

```
advisory
├── counts_toward_overall: false        # sabit
├── label_key: "advisory.estimated"     # arayüz "tahmini" etiketini bundan çözer
├── eeat   { value | null, band, method:"llm-rubric", confidence, evidence_quotes[], rubric_version, cached_from_hash }
└── sxo    { … } | null
```

`advisory` değerleri **trend dışıdır** ve `GET /sites/{id}/history` içinde yer almaz (belge 01 §4, D3).

```
trend
├── basis: "core_sample"
├── comparable_to_audit_id: string | null
├── comparable: bool                    # score_version veya çekirdek örneklem farklıysa false
├── reason_if_not: null | "score_version_changed" | "core_sample_changed" | "first_audit"
└── delta: { overall: number | null, by_category: { <id>: number } } | null
```

### 4.7 `recommendations[]` ve `action_plan`

| Alan | Tip | Not |
|---|---|---|
| `id` | string | `rec_…` |
| `finding_ids[]` | string[] | Bu öneri hangi bulguları çözer |
| `title_key` + `params` | | Çevrilebilir başlık |
| `body` | string | Rapor dilinde açıklama (Katman C veya kural kaydı şablonu) |
| `effort` | `{level: "S"\|"M"\|"L", hours_min, hours_max}` | **Yapılandırılmış**; kaynakta yok `[doğrulandı: 08 §3.3]` |
| `impact` | `{level: "low"\|"medium"\|"high", rationale_key}` | Yapılandırılmış |
| `confidence` | enum | |
| `depends_on[]` | string[] | Bağımlılık grafiği (döngüsüz) |
| `owner_hint` | `dev`\|`content`\|`seo`\|`design`\|`legal` \| null | |
| `priority_score` | number | Türetilmiş, §6 |
| `snippet` | `{type, language, code}` \| null | Faz 2: hazır JSON-LD önerisi |
| `failure_check`, `leading_indicator` | string \| object | "Bunun işe yaramadığını nasıl anlarız" (kaynakta thinking framework'ün ACCEPT/GROW alanları; şemada zorunlu değil, prompt'ta var `[doğrulandı: 08 §13]`). Bizde **önerilir** |

`action_plan.phases[]`: `{id, name_key, timeframe_key, items[{recommendation_id, order, parallelizable_with[]}], exit_criteria_keys[]}`. Sabit 4 faz (§6.1).

### 4.8 Diğer alanlar

| Alan | İçerik |
|---|---|
| `site_facts` | `{robots{status, blocks_entry, ai_bots{…}}, sitemap{status, urls_declared}, transport{tls_ok, hsts, redirects_to_https}}` (özet, ayrıntı bulgularda) |
| `data_sources[]` | `{id: fetch\|render\|psi\|crux\|gsc, status: ok\|missing\|failed, freshness, known_anomalies[]}` |
| `limitations[]` | `{code, message_key, params}`; kodlar: `partial-sample`, `robots-disallows-entry`, `render-failed`, `language-unsupported`, `psi-unavailable`, `tier-capped` |
| `usage` | `{fetch{requests, bytes}, render{pages}, llm{input_tokens, output_tokens, cost_estimate, byok}}`; paylaşılan görünümde **çıkarılır** |
| `quality` | `{status: PASS\|WARN\|FAIL, checks[]}` |
| `exports` | `{html: path, pdf: path\|null}` (kaynaktaki ölü `artifacts.*` alanları yerine) |

### 4.9 Pydantic taslağı `[B]`

```python
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from pydantic import BaseModel, Field, model_validator


class Severity(StrEnum):
    Critical = "Critical"
    High = "High"
    Medium = "Medium"
    Low = "Low"
    Info = "Info"


class Category(StrEnum):
    technical = "technical"
    onpage = "onpage"
    content = "content"
    schema = "schema"
    performance = "performance"
    ai_readiness = "ai_readiness"
    images = "images"


class Layer(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class AuditStatus(StrEnum):
    queued = "queued"
    running = "running"
    partial = "partial"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"


Confidence = Literal["high", "medium", "low"]
Score = Annotated[float, Field(ge=0, le=100)]


class Evidence(BaseModel):
    value: Annotated[str, Field(max_length=200)]  # kontrol/bidi karakterleri temizlenmiş
    truncated: bool = False


class Finding(BaseModel):
    id: str
    check_id: str
    rule_version: str
    category: Category
    layer: Layer
    severity: Severity
    severity_original: Severity | None = None
    severity_reason: str | None = None
    scope: Literal["page", "site"]
    url: str | None = None
    message_key: str
    params: dict[str, str | int | float] = {}
    message: str
    heuristic: bool = False
    evidence: Evidence | None = None
    count: int | None = None
    confidence: Confidence = "high"
    recommendation_ids: list[str] = []

    @model_validator(mode="after")
    def _layer_c_limits(self):
        if self.layer is Layer.C and self.severity in (Severity.Critical,):
            raise ValueError("Katman C bulgusu Critical olamaz")
        return self


class Gate(BaseModel):
    id: str
    cap: Score
    finding_id: str
    url: str | None = None


class OverallScore(BaseModel):
    value: Score | None
    display: Literal["number", "insufficient_data"]
    raw_value: Score | None = None
    coverage_pct: Score
    confidence: Confidence
    gate: Gate | None = None

    @model_validator(mode="after")
    def _consistent(self):
        if self.display == "insufficient_data" and self.value is not None:
            raise ValueError("Yetersiz veride sayı gösterilemez")
        if self.gate and self.value is not None and self.value > self.gate.cap:
            raise ValueError("Skor kapı tavanını aşıyor")
        return self
```

Tam model kümesi (kategori, öneri, plan, sayfa, kaynak, kalite) aynı kalıpla yazılır; JSON Schema `AuditReport.model_json_schema()` ile üretilir ve depoya sürümlü dosya olarak girer (`schemas/audit-1.0.0.json`).

### 4.10 Örnek `audit.json` (kısaltılmış)

```json
{
  "schema_version": "1.0.0",
  "audit": {
    "id": "aud_01HX9Q7B2K3M4N5P6R7S8T9V0W", "parent_audit_id": null,
    "mode": "site", "status": "completed", "tier": "unverified", "locale": "tr",
    "requested_url": "example.com", "final_url": "https://example.com/",
    "site_id": "site_9d3a1c2e5b7f40d8",
    "started_at": "2026-11-13T10:00:02Z", "finished_at": "2026-11-13T10:02:11Z"
  },
  "versions": { "score_version": "mvp-0.1", "rule_version": "1.0", "rubric_version": "1.0", "engine_version": "0.1.0" },
  "target": {
    "origin": "https://example.com", "scope_hosts": ["example.com", "www.example.com"],
    "business_type": { "value": "saas", "confidence": "medium", "signals": ["/pricing", "/features"], "alternatives": [] },
    "language": { "code": "tr", "supported": true, "detected_from": "html-lang" }
  },
  "crawl": {
    "limits": { "max_pages_requested": 50, "max_pages_applied": 25, "reason": "tier_unverified" },
    "coverage": { "pages_discovered": 1840, "pages_planned": 25, "pages_fetched": 24, "pages_rendered": 3,
                  "skipped": { "robots": 1, "error": 1, "out_of_scope": 14 } },
    "templates": [ { "key": "/blog/*", "discovered": 1200, "sampled": 8 } ],
    "sample_seed": "a41c9e"
  },
  "scores": {
    "kind": "health",
    "overall": {
      "value": 40, "display": "number", "raw_value": 71, "coverage_pct": 90, "confidence": "medium",
      "gate": { "id": "noindex-entry", "cap": 40, "finding_id": "fnd_0001", "url": "https://example.com/" }
    },
    "categories": [
      { "id": "technical", "weight_default": 25, "weight_effective": 27.8, "status": "measured",
        "score": 55, "confidence": "high", "checks_total": 20, "checks_run": 20, "checks_failed": 3,
        "penalties": [ { "finding_id": "fnd_0001", "severity": "Critical", "points": -40 } ],
        "not_measured_reason": null, "finding_ids": ["fnd_0001"] },
      { "id": "performance", "weight_default": 10, "status": "not_measured", "score": null,
        "not_measured_reason": "psi-unavailable", "finding_ids": [] }
    ]
  },
  "trend": { "basis": "core_sample", "comparable_to_audit_id": null, "comparable": false, "reason_if_not": "first_audit", "delta": null },
  "advisory": { "counts_toward_overall": false, "label_key": "advisory.estimated",
                "eeat": { "value": 55, "band": "moderate", "method": "llm-rubric", "confidence": "low",
                          "evidence_quotes": [], "rubric_version": "1.0", "cached_from_hash": null },
                "sxo": null },
  "findings": [
    { "id": "fnd_0001", "check_id": "noindex", "rule_version": "1.0", "category": "technical", "layer": "A",
      "severity": "Critical", "scope": "page", "url": "https://example.com/",
      "message_key": "check.noindex", "params": {}, "message": "Bir robots meta etiketi bu sayfanın indekslenmemesini istiyor. Bunun bilinçli olduğunu doğrulayın.",
      "heuristic": false, "evidence": { "value": "noindex, nofollow", "truncated": false },
      "confidence": "high", "recommendation_ids": ["rec_0001"] }
  ],
  "not_checked": [ { "check_id": "title-not-reflected-in-content", "scope": "page", "reason_code": "language-unsupported" } ],
  "recommendations": [
    { "id": "rec_0001", "finding_ids": ["fnd_0001"], "title_key": "rec.remove-noindex", "params": {},
      "body": "Ana sayfadaki noindex yönergesini kaldırın.",
      "effort": { "level": "S", "hours_min": 0.25, "hours_max": 1 },
      "impact": { "level": "high", "rationale_key": "impact.blocks-indexing" },
      "confidence": "high", "depends_on": [], "owner_hint": "dev", "priority_score": 3.0 }
  ],
  "action_plan": { "phases": [
    { "id": "phase-1", "name_key": "plan.phase1", "timeframe_key": "plan.week1",
      "items": [ { "recommendation_id": "rec_0001", "order": 1, "parallelizable_with": [] } ], "exit_criteria_keys": [] },
    { "id": "phase-2", "name_key": "plan.phase2", "timeframe_key": "plan.weeks2-3", "items": [], "exit_criteria_keys": [] },
    { "id": "phase-3", "name_key": "plan.phase3", "timeframe_key": "plan.month2", "items": [], "exit_criteria_keys": [] },
    { "id": "phase-4", "name_key": "plan.phase4", "timeframe_key": "plan.ongoing", "items": [], "exit_criteria_keys": [] }
  ] },
  "data_sources": [
    { "id": "fetch", "status": "ok", "freshness": "live", "known_anomalies": [] },
    { "id": "psi", "status": "missing", "freshness": null, "known_anomalies": [] }
  ],
  "limitations": [ { "code": "tier-capped", "message_key": "limit.tier-capped", "params": { "applied": 25, "requested": 50 } } ],
  "quality": { "status": "PASS", "checks": [] },
  "exports": { "html": "reports/aud_01HX…/index.html", "pdf": null }
}
```

(Örnek, kapı mantığını göstermek için `value = min(raw_value=71, cap=40) = 40` kurar; `weight_effective` yeniden normalize edilmiş ağırlığı gösterir.)

### 4.11 `kaynak analizi notları 08 §15` önerisinden farklar

| Konu | 08 §15 önerisi | Nihai şema | Neden |
|---|---|---|---|
| Severity yazımı | küçük harf (`critical`) | `Critical…Info` büyük harf | Ortak sözleşme enum'ları |
| Bulgu durumu | `fail|warn|pass|not_checked` | Yalnız tespit edilenler `findings[]`'te; `not_checked[]` ayrı; geçenler `passed_check_ids` | `page_checks` modeline uyum, şişmeyi önler |
| Skor | `summary.health_score{value,status,coverage}` | `scores.overall{value,display,raw_value,coverage_pct,confidence,gate}` | Kapı ve "Yetersiz veri" (belge 01 §8.3-8.4) |
| Kapsam | tek `coverage` | `scores.coverage_pct` (kategori) ve `crawl.coverage` (sayfa) ayrı | İki farklı kavram |
| Örneklem | `pages_crawled`, `crawl_limits` | Çekirdek/keşif, `role`, şablon dağılımı, tohum | Belge 00 §3.3, belge 05 §9.4 |
| LLM çıktısı | bulgulara karışık | `advisory` ayrı, `counts_toward_overall:false` | D3 |
| Metin | düz `title`/`description` | `message_key`+`params` (+ çözülmüş `message`) | TR/EN çeviri |
| Sürümleme | `schema_version`, `tool_version` | `schema_version` + `score_version` + `rule_version` + `rubric_version` + `engine_version` | Karşılaştırılabilirlik (belge 01 P5) |
| Kimlik zinciri | yok | `parent_audit_id`, `rerun`, `inherited_from` | Yeniden çalıştırma |
| Trend | yok | `trend{basis,comparable,reason_if_not}` | Çekirdek örneklem |
| Kullanım/maliyet | yok | `usage` | Maliyet görünürlüğü (belge 00 §3.4) |
| Kalite | yok | `quality` | §8 |
| Ölü alanlar | `artifacts.*` korundu | `exports` | Kaynakta `artifacts` hiç okunmuyor `[doğrulandı]` |
| Katman C kısıtı | `source_type=third_party|assumption` Critical olamaz | `layer=C` Critical olamaz, kapıyı tetikleyemez | Katman modeline çevrildi |

### 4.12 kaynak proje `audit-data.json` ↔ `audit.json` eşlemesi

Bir dönüştürücü (yaklaşık 40 satır `[B]`) iki yönde de gerekirse yazılabilir; esas amaç kaynak test fixture'larını ve (varsa) dış araçları beslemektir.

| kaynak proje alanı | Bizim alanımız | Not |
|---|---|---|
| `summary.health_score` | `scores.overall.value` | Kaynakta LLM yazar; bizde kodla hesaplanır `[doğrulandı: 01 §2]` |
| `summary.business_type` | `target.business_type.value` | |
| `summary.top_findings[]` | En yüksek `priority_score`'lu ilk 5 `finding` | Türetilir, saklanmaz |
| `summary.quick_wins[]` | `recommendations` içinde `effort=S` ve `impact≥medium` | Türetilir |
| `categories[].name` | `scores.categories[].id` (+ çeviri) | Kaynakta ad serbest metin; ağırlık tablosuyla bire bir eşleşmiyor `[doğrulandı: 08 §13 #14]` |
| `categories[].score` | `scores.categories[].score` | |
| `categories[].what_works[]` | `passed_check_ids[]` | |
| `categories[].findings[].title/severity/description/recommendation` | `findings[].message` / `severity` / `message` / `recommendations[].body` | |
| `action_plan.phases[].items[]` | `items[].recommendation_id` | Kaynakta düz string, `str()` ile basılır `[doğrulandı]` |
| `artifacts.findings_dir`, `.screenshots_dir` | (yok) | Kaynakta okunmuyor; kaldırıldı |

## 5. Rapor arayüzü: bilgi mimarisi

Sayfa yapısı (üstten alta). Sıra, kaynağın rapor bölüm sırasını korur: yönetici özeti → kategori ayrıntısı → aksiyon planı → metodoloji `[K: 08 §4.2]`.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ example.com · Site denetimi · 13 Kas 2026 10:02 · TR   [Paylaş] [İndir] [⟳]   │
│ score_version mvp-0.1 · kural 1.0                          [Soru sor] [Geçmiş]│
├──────────────────────────────────────────────────────────────────────────────┤
│ ⬣ SKOR SINIRLANDIRILDI: Ana sayfada noindex bulundu (noindex).                │
│   Ham skor 71, bu bulgu yüzünden en çok 40 gösterilir.        [Bulguya git ▸]  │
├───────────────────┬──────────────────────┬───────────────────────────────────┤
│  SAĞLIK SKORU     │  KAPSAM              │  GÜVEN                            │
│     40 /100  ▼    │  %90 (kategori)      │  ORTA                             │
│  [kötü] ⬣         │  24/25 sayfa (örnek) │  Örneklem 25 sayfa, 1 kategori yok│
├───────────────────┴──────────────────────┴───────────────────────────────────┤
│ Yönetici özeti                                                               │
│  Kritik 1 · Yüksek 4 · Orta 9 · Düşük 6 · Bilgi 3                             │
│  ▸ En önemli 5 sorun            ▸ 5 hızlı kazanç (efor S, etki ≥ orta)        │
├──────────────────────────────────────────────────────────────────────────────┤
│ Kategoriler                                                                  │
│ ┌────────────┐┌────────────┐┌────────────┐┌────────────┐                      │
│ │Teknik 55   ││Sayfa içi 78││İçerik 70   ││Schema 90   │  ...                 │
│ │w 27.8 ▲ 3  ││w 22.2      ││w 22.2      ││w 11.1      │                      │
│ └────────────┘└────────────┘└────────────┘└────────────┘                      │
│ ┌ ─ ─ ─ ─ ─ ─ ─ ─ ┐                                                          │
│   Performans · ÖLÇÜLMEDİ ─ PSI verisi alınamadı. Skora katılmadı.             │
│   Nasıl açılır? ▸                                                            │
│ └ ─ ─ ─ ─ ─ ─ ─ ─ ┘                                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│ Bulgular   [Şiddet ▾][Kategori ▾][Katman ▾][Kapsam ▾][Ara…]                  │
│ ⬣ Kritik  noindex · Ana sayfa              kanıt: "noindex, nofollow"  ▸ öneri│
│ ▲ Yüksek  canonical-points-elsewhere · /a   kanıt: https://…/b         ▸ öneri│
│ ◆ Orta    missing-meta-description · 8 sayfa (örneğin %32'si)          ▸ öneri│
│ ● Düşük   multiple-h1 · 3 sayfa · [heuristik]                          ▸ öneri│
├──────────────────────────────────────────────────────────────────────────────┤
│ Aksiyon planı                                                                │
│ Faz 1 Kritik düzeltmeler (Hafta 1)  Faz 2 Yüksek etki (Hf 2-3)                │
│ Faz 3 İçerik ve otorite (Ay 2)      Faz 4 İzleme (sürekli)                    │
├──────────────────────────────────────────────────────────────────────────────┤
│ Danışma değerlendirmesi (TAHMİNİ · skora dahil değil)                         │
│  E-E-A-T 55/100 (orta) · güven: düşük · [alıntılar ▸]                         │
├──────────────────────────────────────────────────────────────────────────────┤
│ Metodoloji ve sınırlar                                                       │
│  Ölçülenler · Ölçülemeyenler · Heuristik uyarılar · Örneklem · Veri kaynakları│
├──────────────────────────────────────────────────────────────────────────────┤
│ Geçmiş ve trend (çekirdek örneklem)   ▁▂▃▅▆ · ┄ score_version 0.1→0.2 kopuş  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5.1 Sayfa analizi (Page Score Card) görünümü

Kaynağın `seo-page` çıktısı 5 kategorili kart gösterir `[K, doğrulandı]`. Bizde aynı kart; fark: kapı bandı, kapsam/güven, `not_checked` listesi ve veri varsa Performans kartı.

```
 Sayfa skoru        72 /100          Kapsam %100 (5 kategori)   Güven: YÜKSEK
 Sayfa içi   ████████░░ 80      İçerik    ███████░░░ 70      Teknik   ██████░░░░ 62
 Schema      █████░░░░░ 50      Görseller ████████░░ 85
 (Performans kartı yalnız PSI/CrUX verisi varsa görünür)
```

### 5.2 "Ölçülmedi" kartı `[B]`

| Öğe | Davranış |
|---|---|
| Görünüm | Kesikli çerçeve, nötr gri, skor yerine "—" ve **"Ölçülmedi"** metni (renk dışında da ayırt edilir) |
| Neden | `not_measured_reason` koduna karşılık gelen, insan okuyabilir cümle (örn. "PSI verisi alınamadı") |
| Etki | "Bu kategori skora katılmadı; kalan kategorilerin ağırlıkları yeniden dağıtıldı." |
| Çıkış | "Nasıl açılır?": gereksinim bağlantısı (örn. doğrulanmış sahip, yeniden çalıştır). Yalnız gerçekten kullanıcının yapabileceği bir şey varsa gösterilir |
| Kural | Hiçbir yerde 0 veya "iyi" olarak boyanmaz, grafikte nokta olarak yer almaz |

### 5.3 Durumlar

| Durum | Gösterim |
|---|---|
| Kuyrukta/çalışıyor | Aşama çubuğu, tahmini süre yok (yalnız aşama ve sayaç), İptal |
| Kısmi (`partial`) | Üstte sabit bilgi bandı: "Rapor kısmi: …neden" + kapsam; skor kuralları aynı |
| **Yetersiz veri** | Skor kartında sayı yerine "Yetersiz veri (kapsam %X)"; bulgular yine listelenir |
| Başarısız (`failed`) | Skor yok; neden (`target-rejected`: "Bu adres genel internetten erişilebilir değil", `unreachable`: yeniden dene önerisi). İç ayrıntı gösterilmez |
| İptal | Kısmi rapor varsa gösterilir, yoksa boş durum |
| Sıfır bulgu | "İncelenen N kontrolde sorun bulunmadı." + **sınır notu**: yalnız ölçülen kontroller kapsanır; `not_checked` listesi gösterilir. Asla "sitenizde sorun yok" denmez |
| Örneklem tek şablon | Güven düşük uyarısı (belge 05 §9.4) |
| Dil desteklenmiyor | "Bu dilde X kontrol yapılamadı" notu (belge 01 §4.0) |
| Paylaşılan görünüm | Salt okunur; Soru sor, yeniden çalıştır, kullanım ve (seçildiyse) kanıt gizli |

## 6. Aksiyon planı üretimi

### 6.1 Fazlar `[K+B]`

Kaynağın dört fazı korunur `[K: seo-audit SKILL.md]`; fazlar arayüzde çevrilmiş anahtarlardır.

| Faz | Zaman | Kaynak adı |
|---|---|---|
| 1 | Hafta 1 | Critical Fixes (Kritik düzeltmeler) |
| 2 | Hafta 2-3 | High-Impact Improvements |
| 3 | Ay 2 | Content & Authority |
| 4 | Sürekli | Monitoring & Iteration |

### 6.2 Faz atama kuralı `[B]`

Deterministik (kod), LLM yok:

1. **Taban faz** bulgu şiddetinden: `Critical→1`, `High→2`, `Medium→3`, `Low/Info→4`. Öneri, çözdüğü bulguların **en yüksek şiddetini** devralır.
2. **Kapı bulgusu** (skoru sınırlayan) her zaman faz 1.
3. **Hızlı kazanç yükseltmesi:** `effort=S` ve `impact≥medium` ve şiddet `≥Medium` ise bir faz öne alınır (en erken faz 1).
4. **Bağımlılık:** `R.depends_on = D` ise `faz(R) ≥ faz(D)`; gerekirse R sonraki faza kayar, **asla öne alınmaz**. Bağımlılık döngüsü doğrulayıcıda reddedilir (§8).
5. Faz içi sıra: `priority_score` azalan; eşitlikte şiddet, sonra `check_id`.
6. Faz 4 `exit_criteria` yerine "izleme" öğeleri (yeniden denetim aralığı, takip edilecek gösterge) taşır.

### 6.3 Efor, etki ve öncelik `[B]`

Kaynakta efor ve etki yapılandırılmış alan değildir; efor, rapor koduna gömülmüş sabit metinlerdir (`Low (30 min)`) `[doğrulandı: 08 §3.3]`. Bizde:

- **Katman A/B bulguları:** efor ve etki **kural kaydından** gelir (tekrarlanabilir). Belge 01 §5 `CheckDef` bu alanlarla genişletilir: `effort_default`, `impact_default`, `message_key`, `references`.
- **Katman C önerileri:** LLM `rationale` üretir; ama **seviye değerleri sabit bir listeden seçilir**, serbest metin değil, ve şema ile doğrulanır.
- `effort.level`: `S` (≤ 1 saat), `M` (yarım-bir gün), `L` (> 1 gün). `hours_min/max` aralığı kayıt ile birlikte gelir.

```
priority_score = impact_w × confidence_w ÷ effort_w
impact_w:     low 1 · medium 2 · high 3
confidence_w: low 0.5 · medium 0.75 · high 1
effort_w:     S 1 · M 2 · L 4
```

Başlangıç değerleridir `[?]`, kalibrasyonla (belge 01 §13.2) gözden geçirilir. **Hızlı kazanç** = `effort S`, `impact ≥ medium`.

## 7. Çıktı biçimleri ve paylaşım

### 7.1 Biçimler

| Biçim | Faz | Üretim | Not |
|---|---|---|---|
| **JSON (`audit.json`)** | 1 | Kanonik | Her şeyin kaynağı |
| **HTML** | 1 | Sunucu tarafı, `audit.json`'dan | Baskı dostu CSS dahil; dış kaynak yok |
| PDF | **3** | HTML'den | §7.3 |
| CSV (bulgular) | 3 (isteğe bağlı) | | Kaynaktaki xlsx yalnız Google verisini kapsıyor, kategori ve eylem planını içermiyor `[doğrulandı: 08 §4.11]` |

### 7.2 HTML üretimi `[B]`

- Jinja2, `autoescape` **zorunlu açık**; sayfa kaynaklı hiçbir değerde `|safe` yok.
- Grafikler (gösterge, çubuk) **sunucuda satır içi SVG** olarak üretilir. Kaynaktaki matplotlib+numpy+pillow zinciri gerekmez `[doğrulandı: requirements.txt]`.
- Rapor kendi kendine yeterli (self-contained) tek HTML olarak saklanabilir; yazı tipi sistem yığını.
- Aynı şablon arayüzde ve paylaşım görünümünde kullanılır (paylaşımda bazı bölümler koşullu gizlenir).

### 7.3 PDF (Faz 3) `[?] IO2`

| Seçenek | Artı | Eksi |
|---|---|---|
| **A: Playwright `page.pdf()`** (önerilen) | Zaten yığında; aynı HTML ve baskı CSS'i; grafikler SVG olduğu için sorunsuz | Tarayıcı kaynağı; render worker'ı ile **aynı güvenlik katmanı** gerekir |
| B: WeasyPrint (kaynak yöntemi) | Hafif süreç, baskı CSS desteği iyi | Pango/Cairo sistem kütüphaneleri; kaynaktaki bağımlılık yükü (weasyprint, matplotlib, numpy, pillow, openpyxl) ve `page-break-inside: avoid` kaynaklı boşluk sorunu `[K, 08 §4.7]` |

Güvenlik: PDF üretimi **kendi HTML'imizi** `set_content` ile yükler, **ağ tamamen kapalıdır** (tüm istekler iptal), çünkü içeriğe sayfadan gelen metin girmiştir. PDF worker'ı render worker'ından ayrı bağlamdadır (belge 05 §5.3). Kaynaktaki PDF kural sırası (kapak, içindekiler, özet, veri bölümleri, öneriler, metodoloji; A4, her bölüm yeni sayfa) `[K]` baskı CSS'ine taşınır.

### 7.4 Paylaşılabilir bağlantı `[B]`

| Konu | Karar |
|---|---|
| Biçim | `https://app.<alan-adı>/r/<belirteç>`; belirteç ≥128 bit rastgele, **HMAC imzalı** ve veritabanında iptal edilebilir kayıtla eşli |
| Süre | Varsayılan 7 gün, en çok 30 gün (IO3); süresi dolan bağlantı `410` |
| Yetki | Salt okunur. Soru sor, yeniden çalıştır, kullanım/maliyet ve (seçenekle) `evidence` **gizli** |
| İndeksleme | `X-Robots-Tag: noindex, nofollow`, `Referrer-Policy: no-referrer`, `Cache-Control: private, no-store` |
| İptal | Anında (kayıt silinir/işaretlenir) |
| Gizlilik notu | Rapor başkasının sitesine ait olabilir; bağlantıyı alan herkes bulguları görür. Arayüz bunu açıkça söyler |

## 8. Rapor kalite kapısı

`report` aşamasında, rapor yayınlanmadan önce çalışır; sonuç `audit.quality` içine yazılır.

### 8.1 Kontroller

| Grup | Kontrol | Hata |
|---|---|---|
| **Şema** | `AuditReport` Pydantic doğrulaması + JSON Schema | FAIL |
| **Sözleşme** | `scores.overall.value` kapı tavanını aşmaz; `display=insufficient_data` iken `value=null`; kapsam<60 kuralı; `advisory.counts_toward_overall=false` | FAIL |
| | `score!==null` ancak `status ∈ {measured, partial}`; `not_measured` kategori puanı yok | FAIL |
| | Her `fail` bulgunun `evidence`'ı var (Katman A/B); `not_checked` ne bulguya ne skora girmiş | FAIL |
| | Katman C bulgusu `Critical` değil, kapı/ceza kaynağı değil | FAIL |
| **Referanslar** | Tüm `*_ids` çözülür; `depends_on` döngüsüz; faz öğeleri geçerli öneriye işaret eder | FAIL |
| **Metin** | Her `message_key` hem `tr` hem `en` kataloğunda var; parametreler eksiksiz | FAIL (rapor dilinde eksik) / WARN (diğer dil) |
| **HTML** | Boş `src`/`href` yok; başvurulan her yerel varlık çözülür; başlık hiyerarşisi atlamaz; yinelenen bölüm/tablo yok; bölüm asgari içerik | WARN |
| | **Kaçışlama:** testte enjekte edilen işaretleme sentinel'i (`<script>`, `"><img onerror>`) çıktıda **kaçışlanmış** olmalı | FAIL |
| **Erişilebilirlik** | axe-core (Playwright) kritik/ciddi ihlal yok, CI'da referans rapor fixture'ları üzerinde | CI'da FAIL |
| **PDF** (Faz 3) | Sayfa sayısı makul aralıkta; yatay taşma yok (`scrollWidth>clientWidth` ölçümü); yazı tipi gömülü | WARN |

Karar: `FAIL` → rapor **sunulmaz**, denetim `partial` kalır, API `report-invalid` döner, içeride alarm; `WARN` → sunulur, günlüğe yazılır, `quality.checks` içinde görünür; `PASS` → normal.

### 8.2 Kaynaktaki `_review_pdf` ile karşılaştırma `[doğrulandı]`

| Konu | kaynak proje | Bizde |
|---|---|---|
| İncelenen şey | Yalnız **HTML dizesi** | Şema + sözleşme + HTML + (Faz 3) PDF çıktısı |
| Boş görüntü | Yalnız `src=""` regex'i | Tüm yerel varlık referansları çözülür |
| Kırık dosya yolu / taşma | Yakalanmaz | Taşma ölçümü (Faz 3), varlık çözümü |
| Sayfa sayısı | `pypdf` opsiyonel; yoksa "issue" sayılıp durum `WARN` olur (`requirements.txt`'te yok) | Zorunlu bağımlılık veya Playwright ölçümü |
| Karar etkisi | "PASS olmadan sunma" kuralı CLAUDE.md'de metindir; kod `WARN` döndürüp yine yazar | `FAIL` **gerçekten engeller** |
| Şema/sözleşme | Yok | Var |

## 9. Erişilebilirlik ve çok dillilik

### 9.1 Hedef
WCAG 2.2 AA. Klavye ile tam gezinti, görünür odak, anlamlı başlık/ landmark yapısı, tablolarda `th scope`, grafiklerde metin eşdeğeri, `prefers-reduced-motion` için ilerleme animasyonu yok, `prefers-color-scheme` ile koyu tema.

### 9.2 Şiddet haritası `[B]`

Kaynakta Critical/High/Medium/Low/Info raporda aynı amber sınıfını alır; çünkü `_rating_css_class` yalnız `good|pass` ve `poor|fail` eşler, gerisi `status-warn`'dur, bulgu kartı sınıfı da sabit `action-item medium`'dur `[doğrulandı: google_report.py:87-94, 1136, 1142-1143]`. Kaynak paletinin kendisi de metin için zayıftır: amber `#d4740e` beyazda 3.33:1, altın `#b8860b` 3.25:1 (WCAG normal metin eşiği 4.5:1), amber ile kırmızı arasındaki oran yalnız 1.64:1 `[bu turda hesaplandı]`.

Bizim haritamız: **her şiddet = farklı ton + farklı şekil + metin etiketi.** Kontrast oranları WCAG 2.x göreli parlaklık formülüyle hesaplandı.

| Şiddet | Şekil (ikon) | Etiket (TR / EN) | Açık tema metin / zemin tonu | Oran (metin÷beyaz / metin÷ton) | Koyu tema metin / zemin tonu | Oran (metin÷`#111827` / metin÷ton) |
|---|---|---|---|---|---|---|
| Critical | ⬣ dolu sekizgen + ünlem | Kritik / Critical | `#b42318` / `#fdeceb` | 6.57 / 5.75 | `#ff8b83` / `#3b1614` | 7.83 / 7.07 |
| High | ▲ dolu üçgen | Yüksek / High | `#a8480a` / `#fdf0e3` | 5.84 / 5.21 | `#ffa766` / `#3a2210` | 9.27 / 7.75 |
| Medium | ◆ dolu eşkenar dörtgen | Orta / Medium | `#7a5b00` / `#fbf3d4` | 6.32 / 5.68 | `#f0cf5b` / `#352b0a` | 11.64 / 9.18 |
| Low | ● dolu daire | Düşük / Low | `#1d5bbf` / `#e8f0fc` | 6.36 / 5.54 | `#8ab4ff` / `#14264a` | 8.49 / 7.15 |
| Info | ⓘ içi boş daire + i | Bilgi / Info | `#475467` / `#eef0f3` | 7.69 / 6.73 | `#b4bcc9` / `#242b38` | 9.27 / 7.43 |

Kurallar:
- Tüm metin/zemin çiftleri ≥ 4.5:1 (en düşük 5.21); ton zeminleri tek başına ayırt edici değildir (beyaza göre ~1.1:1), bu yüzden **ikon ve etiket zorunludur**.
- Şiddet sıralaması **konumla** da iletilir (liste şiddete göre sıralı, kapsayıcı başlıklarda sayaç).
- Renk körlüğü: kırmızı/turuncu/sarı-kahve üçlüsü bazı görme tiplerinde yakınlaşabilir. Bu yüzden şekil ve etiket birincildir. **CVD simülasyonu bu turda yapılmadı** `[?]`; arayüz uygulanırken test edilecek.
- Skor bandı (yalnız gösterim): ≥80 iyi `#1b6b43`, 50-79 dikkat `#8f5300`, <50 kötü `#b42318` (beyaz metinle 6.5 / 6.17 / 6.57:1); **bant sınırları tahmindir** `[?] IO7` ve `score_version`'a bağlıdır. Kaynaktaki iki farklı eşik (gösterge ≥90, rozet ≥80) `[doğrulandı: _score_color / _score_class]` tek sete indirilir. Ölçülmedi/Yetersiz veri nötr gridir ve bir bant değildir.
- Marka tonları (kaynak): lacivert `#1e3a5f` (beyazda 11.5:1) başlıklara uygundur; altın yalnız dekoratif kullanılır, metin için değil.

### 9.3 Çok dillilik

| Konu | Karar |
|---|---|
| Diller | `tr`, `en` (varsayılan: kullanıcı tercihi, yoksa tarayıcı; belge 05 `Accept-Language` konusu **sitenin dilini** ilgilendirir, rapor dilinden ayrıdır) `[B]` |
| Katalog | `message_key` → TR/EN metin; parametreler adlandırılmış; çoğul ve sayı/tarih biçimleri yerel ayarla |
| Kural metinleri | Kural kaydında sabit (Katman A/B); arama motoru kuralı olmayan heuristikler "heuristik" notuyla `[K]` |
| Katman C metni | Rapor dili istem parametresidir; çıktı şema ile doğrulanır, önbellek anahtarına dil eklenir |
| Türkçe büyük/küçük harf | Kod tarafında `str.upper()` ile başlık üretilmez (`i`→`I` hatası); büyük harf CSS `text-transform` ve doğru `lang="tr"` ile yapılır |
| Eksik çeviri | Rapor dilinde eksikse FAIL, diğer dilde WARN (§8) |
| Site dili ≠ rapor dili | Tamamen bağımsız: Türkçe site İngilizce raporla incelenebilir; `target.language` yalnız dile bağlı kontrolleri etkiler (belge 01 §4.0) |

## 10. Güvenlik

| Tehdit | Kaynak | Önlem |
|---|---|---|
| **Depolanmış XSS** (rapor/PDF) | `evidence`, URL, başlık, `message` parametreleri sayfadan gelir | Jinja2 `autoescape` zorunlu, `|safe` yasak; `evidence` üretimde kontrol/bidi karakterlerinden arındırılır ve 200 karaktere kırpılır `[K: page_checks._trim ve _CONTROL_RE, doğrulandı]`; render testleri sentinel enjekte eder (§8). Kaynak rapor kodu da kaçışlama yapar (`html.escape`) `[doğrulandı: google_report.py:21, 1108-1143; drift_report.py:54-58]`, ama bunu test etmez |
| Zararlı bağlantı | Bulgudaki URL `javascript:` olabilir | Yalnız `http/https` bağlantı olur, diğerleri düz metin; `rel="noopener noreferrer nofollow"`; `target=_blank` yalnız dış site örneklerinde |
| **Prompt injection (Q&A, Katman C)** | `evidence` ve sayfa metni | Veri bloğu olarak çevrelenir, talimat sayılmaz `[K]`; cevap atıf doğrulamasından geçer; model çıktısı kısıtlı işaretleme ile sınırlanır (görüntü/ham HTML/harici bağlantı yok) |
| IDOR | Tahmin edilebilir kimlik | Kiracı kapsamı + öneki rastgele kimlikler; başka kiracıya ait kaynak `404` |
| Paylaşım sızıntısı | Süresiz bağlantı | İmzalı, süreli, iptal edilebilir; `no-store`, `noindex` |
| Anahtar sızıntısı | BYOK ve API anahtarı | Şifreli saklama, yanıt/log'a hiç yazılmaz, yalnız `last4`; API anahtarı yalnız hash |
| Tarayıcı güvenliği | | **CSP:** `default-src 'none'; script-src 'self' 'nonce-…'; style-src 'self' 'nonce-…'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`. Paylaşım görünümünde `connect-src 'none'`. Ek: `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy` kısıtlı |
| CSRF | Oturum çerezi | `SameSite=Lax` + durum değiştiren isteklerde belirteç; Bearer isteklerinde gerekmez |
| SSE | Uzun ömürlü bağlantı | Her bağlantıda kimlik kontrolü; bağlantı başına zaman sınırı; yeniden bağlanma `Last-Event-ID` |
| Hata sızıntısı | Hata ayrıntısı | `target-rejected` hangi iç adres/kuralın tetiklendiğini söylemez (belge 05 §5) |
| PDF üreticisi | Sayfa kaynaklı içerik tarayıcıya girer | Ağ kapalı, ayrı bağlam (§7.3) |
| Bu belgede **SSRF yok** | Rapor katmanı dışa istek yapmaz | Giriş URL'sinin SSRF denetimi belge 05'dedir; rapor arayüzü ve PDF yalnız kendi içeriğini işler |

## 11. Doğrulama matrisi (kaynak ↔ bu belge)

| İddia | Kontrol | Sonuç |
|---|---|---|
| `audit-data.json` için makine-okunur şema yok | `schema/` dizininde yalnız `templates.json` (JSON-LD şablonları); repoda `jsonschema` veya `audit-data` şeması aranıp bulunamadı | ✅ |
| `artifacts` anahtarı rapor kodunda okunmuyor | `grep artifacts scripts/google_report.py` boş | ✅ |
| Şiddet etiketi: `Critical/High/Medium/Low/Info` aynı amber | `_rating_css_class` yalnız `good/pass` ve `poor/fail` eşler, gerisi `status-warn` (`google_report.py:87-94`); bulgu rozeti bu fonksiyonu kullanır (`:1142-1143`) | ✅ |
| Bulgu kartı sınıfı sabit `action-item medium` | `google_report.py:1136` | ✅ |
| Aksiyon planı `items` düz metin | Kaynak fazlar `str()` ile basılır (08 §2.1; kod bu turda satır satır yeniden okunmadı) | ⚠️ 08 notuna dayanır |
| İki farklı skor eşiği (90 ve 80) | `_score_color`: ≥90/≥50; `_score_class`: ≥80/≥50 (`:60-75`) | ✅ |
| `summary.health_score` sayısal değilse çöker | `float(health_score)` `try/except` olmadan (`:1233`) | ✅ |
| `_review_pdf` yalnız HTML dizesini inceler; `pypdf` opsiyonel | `_review_pdf(pdf_path, html_content)` (`:2422`); `pypdf` içe aktarımı `:2438`, eksikse "pypdf missing" issue'su (`:2442`); `requirements.txt`'te `pypdf` yok | ✅ |
| `requirements.txt` ağır rapor bağımlılıkları | matplotlib, numpy, weasyprint, openpyxl, pillow satırları | ✅ |
| Kaynak HTML çıktısını kaçışlıyor | `from html import escape` (`:21`); bulgu başlığı/açıklama/öneri `escape` ile (`:1131-1143`); `drift_report._escape` `html.escape` kullanır (`:54-58`) | ✅ |
| `evidence` temizleme: kontrol/bidi ve 200 karakter | `page_checks._CONTROL_RE`, `_trim`, `EVIDENCE_MAX_CHARS=200` (`:120, 283, 297-302`) | ✅ |
| Marka paleti ve tonlar | `BRAND` sözlüğü (`google_report.py:46-55`); drift paleti ve `SEVERITY_COLORS` (`drift_report.py:24-47`) | ✅ |
| Kaynak paletinin kontrastı yetersiz (amber 3.33, altın 3.25, kırmızı/amber 1.64) | WCAG 2.x göreli parlaklık formülüyle bu turda hesaplandı | ✅ (hesaplama) |
| Önerilen şiddet haritasının kontrast oranları | Aynı hesaplama; tablo §9.2'dedir | ✅ (hesaplama) |
| Efor/etki şemada yok, efor sabit metin | 08 §3.3 (kod sabit dizeleri, bu turda yeniden okunmadı) | ⚠️ 08 notuna dayanır |
| Üç bulgu şeması, üç severity sözlüğü | 08 §2.4; `page_checks` `SEVERITY_ORDER`, `drift` `CRITICAL/WARNING/INFO` (`drift_report.py:37-40`) | ✅ |
| Methodology tablosu koşulsuz Google kaynaklarını sayar | 08 §4.10 (kod bu turda yeniden okunmadı) | ⚠️ 08 notuna dayanır |
| Google logosu eksik, XLSX'in kapsamı | 08 §4.6, §4.11 | ⚠️ 08 notuna dayanır |

**Doğrulanmadı / bu turda okunmadı:** `google_report.py`'nin CSS'inde `max-height: 120mm` kuralı; XLSX üretiminin ayrıntıları; `_build_recommendations` içeriği (08'e dayanır); RateLimit başlıklarının güncel IETF adları; SSE'nin ters vekil (reverse proxy) arkasındaki davranışı; CVD simülasyonu; TR/EN kataloğunun gerçek metinleri (yazılacak).

## 12. Açık kararlar

| # | Karar | Öneri | Etki |
|---|---|---|---|
| **IO1** | Arayüz teknolojisi | Başlangıçta sunucu tarafı HTML (Jinja2) + hafif etkileşim (ör. htmx benzeri); ayrı TypeScript SPA ihtiyaç doğarsa sonra. Backend Python kalır, API zaten ayrık | Geliştirme hızı, ekip yetkinliği |
| **IO2** | PDF motoru (Faz 3) | Playwright `page.pdf()` + ağ kapalı ayrı bağlam | Bağımlılık ve güvenlik |
| **IO3** | Paylaşım bağlantısı varsayılanları | 7 gün, en çok 30; `hide_evidence` varsayılan **kapalı** ama seçenek var | Gizlilik, kullanım kolaylığı |
| **IO4** | Katman C yeniden çalıştırma ve Q&A için saklanan çıkarılmış alan süresi | 30 gün (tahmin); süre dolunca `snapshot-expired` | Depolama, gizlilik; belge 04 |
| **IO5** | Q&A kotası (denetim başına soru, token) | Plan bazlı; başlangıç denetim başına 20 soru | Maliyet |
| **IO6** | Rapor dili varsayılanı | Kullanıcı hesabı dili; yoksa TR | UX |
| **IO7** | Skor bandı eşikleri (80/50) | Kalibrasyon sonrası yeniden değerlendir; `score_version`'a bağla | Algı |
| **IO8** | `GET /rules` herkese açık olsun mu | Evet (şeffaflık; kural kayıtları gizli değil) | Güven, rakip görünürlüğü |
| D2, D4 (belge 01) | Kapsam eşiği %60; iş tipi profilleri kapalı | Değişmedi | |
| D8, D10, D11 (belge 05) | Robots/giriş URL'i, bot kimliği, sahiplik/kota | Bekliyor | `tier`, `limits`, doğrulama uçları bunlara bağlı |

## 13. Sonraki belgeler

| Belge | Konu | Bu belgeden devraldığı |
|---|---|---|
| [`02-agent-arhitecture.md`](02-agent-arhitecture.md) | İş hattı, aşamalar (`stage` enum), fan-out, checkpoint, LLM çağrıları, bütçe | Durum makinesi (§3.4), SSE olayları, yeniden çalıştırma kuralları |
| [`04-data-model.md`](04-data-model.md) | `audit`, `page`, `finding`, `score`, `share`, `site_verification`, saklama | §4 şeması, **IO4** saklama, kiracı izolasyonu, imzalı bağlantı tablosu |
| [`07-features.md`](07-features.md) | Özellik kataloğu | F-xx özellik kimlikleri ve plan matrisi |
| [`08-file-structure.md`](08-file-structure.md) | Dosya yapısı | `report/`, `api/` modülleri, şablon ve CI kapıları (axe-core) |
| [`09-implementation-roadmap.md`](09-implementation-roadmap.md) | Faz faz uygulama | Rapor kalite kapısı, golden raporlar |
