# 04. Veri Modeli

> Durum: **Taslak v0.1** · Önceki belgeler: [`00-capability-parity.md`](00-capability-parity.md) (v0.2), [`01-evaluation-system.md`](01-evaluation-system.md) (v0.2), [`05-system-design.md`](05-system-design.md) (v0.2)
> İşaretler: `[K]` kaynak projeden alındı · `[B]` bizim kararımız · `[?]` açık karar · `[doğrulandı]` kaynak kodla kontrol edildi
> Yığın (ortak sözleşme): Python ≥ 3.11, FastAPI, SQLAlchemy 2 + Alembic, PostgreSQL 16, Redis, Arq, aiohttp, Playwright (async), Pydantic v2, S3 uyumlu nesne depolama. Kütüphane seçimleri `[B]` önerisidir; sürüm ve olgunluk uyumu **doğrulanmadı**.

---

## 1. Amaç ve ilkeler

Bu belge, belge 01'deki **bulgu / skor / kapsam / güven** sözleşmesini, belge 05'deki **fetch sonucu / örneklem / not_checked** sözleşmesini ve belge 00'daki **Q&A, çekirdek-keşif örneklemi, BYOK, önbellek** kararlarını kalıcı depoya çevirir.

| # | İlke | Sonuç |
|---|---|---|
| V1 | **Ölçüm değiştirilemez.** Bulgu, skor, not_checked bir kez yazılır, güncellenmez `[B]` | Tekrarlanabilirlik (belge 01 P5). Yeniden hesap = yeni satır (§4) |
| V2 | **Kiracı sınırı veritabanında zorlanır.** `tenant_id` + bileşik FK + RLS `[B]` | Uygulama hatası başka kiracının verisini sızdırmaz |
| V3 | **Büyük ve geçici veri nesne depolamada**, kalıcı ve sorgulanabilir veri PostgreSQL'de | Ham HTML 30 gün, bulgu ve skor süresiz (`[?]` süre) |
| V4 | **Enum = `text` + `CHECK`**, PostgreSQL `ENUM` tipi değil `[B]` | Yeni değer eklemek `ALTER TYPE` kilidi ve geri dönüşsüz göç gerektirmez |
| V5 | **Her sürüm bir satırdır** (`rule_versions`, `score_versions`) `[B]` | Eski rapor, hangi kural ve formülle üretildiğini kendi içinde taşır |
| V6 | **LLM çıktısı ölçümden ayrı tabloda** (`advisory_scores`, `finding_advice`) `[B]` | Katman C (belge 01 §4) genel skora ve değiştirilemez bulgulara karışmaz |
| V7 | **Sırlar (BYOK) zarf şifreli**, hiçbir log ve sorgu çıktısında görünmez `[B]` | §3.19, §5 |
| V8 | **Kapsam dışı:** faturalama ayrıntısı, kimlik doğrulama sağlayıcısı. `users`/`tenants` yalnız asgari alanları taşır | Belge 05 / ayrı iş |

**Kimlikler:** UUIDv7, **uygulama tarafında** üretilir (zaman sıralı, indeks dostu). PostgreSQL 16'da yerel `uuidv7()` yoktur `[doğrulandı değil: bilgi; sürüm notlarından kontrol edilmeli]`; kolon tipi `uuid`, `DEFAULT` yok. Üretici kütüphane seçimi `[?]` (DM4).

## 2. İlişki diyagramı

```
 tenants 1───* users
    │
    ├──* sites 1───* site_verifications            (Faz 2)
    │       │
    │       └──* audits ◄── parent_audit_id (kendine, yeniden çalıştırma)
    │              │
    │              ├──* audit_stages
    │              ├──* audit_pages ──* page_fetches ──► [nesne depolama: html/robots/sitemap]
    │              │       │
    │              │       ├──* findings ──* finding_advice (Katman C, Faz 2)
    │              │       ├──* not_checked
    │              │       └──* page_scores
    │              ├──* category_scores   (score_version, basis: all|core|page)
    │              ├──* audit_scores      (score_version başına bir satır)
    │              ├──* advisory_scores   (Faz 2)
    │              ├──* page_extracts     (Faz 2b)
    │              ├──* reports ──► [nesne depolama: json/html/pdf]
    │              ├──* llm_calls ──► llm_cache (Faz 2)
    │              └──* qa_threads 1──* qa_messages (Faz 2)
    │
    ├──* usage_ledger        (append-only, kotalar ve maliyet)
    ├──* byok_keys           (Faz 2)
    └──* monitoring_schedules, drift_baselines, drift_events   (Faz 3)

 Global (kiracısız):  rule_versions   score_versions
```

Zincirin belge 01 / 02 ile karşılığı:

| Akış (belge 05 §3) | Yazılan tablo |
|---|---|
| `validate`, `fetch_entry` | `audits` (`final_origin`), `audit_stages`, `page_fetches` |
| `robots`, `discovery` | `page_fetches` (`kind=robots/sitemap`), `audit_pages` (planlanan) |
| `sample` | `audit_pages.sample_kind`, `audits.sample_seed`, `audits.coverage` |
| `fetch_pages`, `render` | `page_fetches`, `audit_pages.fetch_state` |
| `measure` | `findings`, `not_checked` |
| `score` | `page_scores`, `category_scores`, `audit_scores` |
| `advise`, `synthesize` | `llm_calls`, `advisory_scores`, `finding_advice`, `llm_cache` |
| `report` | `reports` |

## 3. Tablo tanımları (PostgreSQL DDL taslağı)

Ortak sözleşmeler:
- Her kiracı tablosunda `tenant_id uuid NOT NULL`.
- Ebeveyn tablolarda `UNIQUE (tenant_id, id)`, çocuklarda **bileşik FK** `(tenant_id, parent_id)`: yanlış kiracıya referans veritabanı seviyesinde imkânsızdır `[B]`.
- Zaman damgaları `timestamptz`, UTC.
- Silme ilişkileri `ON DELETE` belirtilmez (`NO ACTION`): silme işi bağımlılık sırasıyla açıkça yapılır (§6.4).

### 3.1 `tenants`, `users`

```sql
CREATE TABLE tenants (
  id          uuid PRIMARY KEY,
  name        text        NOT NULL,
  plan        text        NOT NULL DEFAULT 'free'   CHECK (plan IN ('free','pro','team')),  -- isimler geçici
  status      text        NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','deleting')),
  settings    jsonb       NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now(),
  deleted_at  timestamptz
);

CREATE TABLE users (
  id           uuid PRIMARY KEY,
  tenant_id    uuid        NOT NULL REFERENCES tenants(id),
  email        text        NOT NULL,
  role         text        NOT NULL DEFAULT 'member' CHECK (role IN ('owner','admin','member')),
  created_at   timestamptz NOT NULL DEFAULT now(),
  disabled_at  timestamptz,
  UNIQUE (tenant_id, id)
);
CREATE UNIQUE INDEX users_email_uq ON users (tenant_id, lower(email));
```

### 3.2 `sites`, `site_verifications`

Sahiplik doğrulama **site** düzeyindedir (bir kiracı bir siteyi doğrular), kullanıcı düzeyinde değil. Ortak sözleşmedeki "tier (kullanıcı)" ifadesinden bilinçli sapmadır, bkz. §11 DM9.

```sql
CREATE TABLE sites (
  id            uuid PRIMARY KEY,
  tenant_id     uuid        NOT NULL REFERENCES tenants(id),
  origin        text        NOT NULL,                  -- https://www.example.com (redirect sonrası son origin)
  host          text        NOT NULL,                  -- www.example.com
  tier          text        NOT NULL DEFAULT 'unverified' CHECK (tier IN ('unverified','verified')),
  business_type text        CHECK (business_type IN ('saas','local','ecommerce','publisher','agency','other')),
  language      text,                                  -- BCP 47 etiketi, ör. 'tr', 'en'
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, origin)
);

CREATE TABLE site_verifications (                      -- Faz 2
  id               uuid PRIMARY KEY,
  tenant_id        uuid        NOT NULL,
  site_id          uuid        NOT NULL,
  method           text        NOT NULL CHECK (method IN ('dns_txt','meta_tag','file')),
  token            text        NOT NULL,
  status           text        NOT NULL DEFAULT 'pending'
                               CHECK (status IN ('pending','verified','failed','revoked')),
  created_at       timestamptz NOT NULL DEFAULT now(),
  last_checked_at  timestamptz,
  verified_at      timestamptz,
  expires_at       timestamptz,
  FOREIGN KEY (tenant_id, site_id) REFERENCES sites (tenant_id, id)
);
CREATE UNIQUE INDEX site_verifications_one_verified
  ON site_verifications (site_id) WHERE status = 'verified';
```

`sites.tier`, `site_verifications` durumundan türetilen **önbellek** alanıdır; uygulama tek noktadan günceller `[B]`. Süresi dolan doğrulama `tier`'i `unverified`'a çeker.

### 3.3 `rule_versions`, `score_versions` (global, kiracısız)

```sql
CREATE TABLE rule_versions (
  version         text PRIMARY KEY,                 -- '1.0', '1.1' ...
  released_at     timestamptz NOT NULL,
  registry        jsonb       NOT NULL,             -- kural kaydı anlık görüntüsü (belge 01 §5)
  registry_sha256 text        NOT NULL,
  changelog       text,
  CHECK (jsonb_typeof(registry) = 'array')
);

CREATE TABLE score_versions (
  version          text PRIMARY KEY,                -- 'mvp-0.1' (belge 01 §8, §15.6)
  released_at      timestamptz NOT NULL,
  rule_version_min text REFERENCES rule_versions(version),
  config           jsonb       NOT NULL,            -- ağırlıklar, taban cezalar, tavanlar, kapılar
  config_sha256    text        NOT NULL,
  changelog        text,
  CHECK (jsonb_typeof(config) = 'object')
);
```

İçerikleri §4.2'de.

### 3.4 `audits`

```sql
CREATE TABLE audits (
  id               uuid PRIMARY KEY,
  tenant_id        uuid        NOT NULL REFERENCES tenants(id),
  site_id          uuid        NOT NULL,
  requested_by     uuid,
  mode             text        NOT NULL CHECK (mode IN ('site','page')),
  target_url       text        NOT NULL,            -- kullanıcının girdiği, normalize edilmiş URL
  final_origin     text,                            -- redirect sonrası; fetch_entry'den sonra dolar
  status           text        NOT NULL DEFAULT 'queued'
                               CHECK (status IN ('queued','running','partial','completed','failed','canceled')),
  score_version    text        NOT NULL REFERENCES score_versions(version),   -- kullanıcıya gösterilen birincil sürüm
  rule_version     text        NOT NULL REFERENCES rule_versions(version),
  sample_seed      bigint,                          -- belge 05 §9.4: aynı tohum = aynı örneklem
  coverage         jsonb       NOT NULL DEFAULT '{}',   -- belge 05 §9.4 şeması
  gate             jsonb,                           -- {id, cap}; kapı yoksa NULL
  confidence       text        CHECK (confidence IN ('high','medium','low')),
  business_type    text        CHECK (business_type IN ('saas','local','ecommerce','publisher','agency','other')),
  language         text,
  budget           jsonb       NOT NULL DEFAULT '{}',   -- {max_pages, max_bytes, max_seconds, llm_tokens, ...}
  cost             jsonb       NOT NULL DEFAULT '{}',   -- gerçekleşen: {requests, bytes, renders, llm_usd}
  parent_audit_id  uuid,                            -- yeniden çalıştırma / yeniden hesap zinciri
  rerun_stages     text[],                          -- modül yeniden çalıştırmada hangi aşamalar
  cancel_requested boolean     NOT NULL DEFAULT false,
  error            jsonb,                           -- {code, message}; failed/partial gerekçesi
  created_at       timestamptz NOT NULL DEFAULT now(),
  started_at       timestamptz,
  finished_at      timestamptz,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, site_id)         REFERENCES sites  (tenant_id, id),
  FOREIGN KEY (tenant_id, requested_by)    REFERENCES users  (tenant_id, id),
  FOREIGN KEY (tenant_id, parent_audit_id) REFERENCES audits (tenant_id, id),
  CHECK (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at),
  CHECK (gate IS NULL OR ((gate ->> 'id') IS NOT NULL AND (gate ->> 'cap') IS NOT NULL)),
  CHECK (jsonb_typeof(coverage) = 'object')
);
CREATE INDEX audits_site_time   ON audits (tenant_id, site_id, created_at DESC);
CREATE INDEX audits_active      ON audits (status, created_at) WHERE status IN ('queued','running');
CREATE INDEX audits_parent      ON audits (parent_audit_id) WHERE parent_audit_id IS NOT NULL;
```

`coverage` örneği (belge 05 §9.4 ile aynı): `{"pages_discovered":1840,"pages_planned":50,"pages_fetched":47,"pages_rendered":6,"templates":[{"key":"/blog/*","discovered":1200,"sampled":18}],"skipped":{"robots":3,"error":2,"out_of_scope":14}}`.

`audits` **değiştirilebilir** bir tablodur (durum, zaman damgaları, `cost`, `coverage` aşama aşama dolar). Ölçüm sonuçları ise alt tablolardadır ve değiştirilemez (§4).

### 3.5 `audit_stages`

```sql
CREATE TABLE audit_stages (
  id          uuid PRIMARY KEY,
  tenant_id   uuid        NOT NULL,
  audit_id    uuid        NOT NULL,
  stage       text        NOT NULL CHECK (stage IN
                ('validate','fetch_entry','robots','discovery','sample','fetch_pages',
                 'render','measure','score','advise','synthesize','report')),
  status      text        NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending','running','done','skipped','failed')),
  attempt     smallint    NOT NULL DEFAULT 1,
  is_partial  boolean     NOT NULL DEFAULT false,      -- kısmi bulgu/checkpoint yazıldı (belge 05 §10)
  checkpoint  jsonb,                                   -- devam için küçük durum (ör. kalan URL sayısı)
  error       jsonb,
  started_at  timestamptz,
  finished_at timestamptz,
  FOREIGN KEY (tenant_id, audit_id) REFERENCES audits (tenant_id, id),
  UNIQUE (audit_id, stage, attempt)
);
CREATE INDEX audit_stages_audit ON audit_stages (audit_id, stage);
```

### 3.6 `audit_pages`

```sql
CREATE TABLE audit_pages (
  id              uuid PRIMARY KEY,
  tenant_id       uuid        NOT NULL,
  audit_id        uuid        NOT NULL,
  url             text        NOT NULL,
  url_match_key   text        NOT NULL,        -- page_checks.url_match_key mantığı (§10)
  template_key    text,                        -- '/blog/*' (belge 05 §9.4)
  sample_kind     text        NOT NULL CHECK (sample_kind IN ('core','exploration')),
  is_entry        boolean     NOT NULL DEFAULT false,
  source          text        NOT NULL CHECK (source IN ('entry','sitemap','link','user')),
  depth           smallint,
  fetch_state     text        NOT NULL DEFAULT 'planned'
                              CHECK (fetch_state IN ('planned','fetched','skipped','failed')),
  skip_reason     text        CHECK (skip_reason IN ('robots','error','out_of_scope','budget')),
  rendered        boolean     NOT NULL DEFAULT false,
  created_at      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, audit_id) REFERENCES audits (tenant_id, id),
  UNIQUE (tenant_id, id),
  UNIQUE (audit_id, url_match_key),
  CHECK ((fetch_state = 'skipped') = (skip_reason IS NOT NULL))
);
CREATE INDEX audit_pages_kind     ON audit_pages (audit_id, sample_kind);
CREATE INDEX audit_pages_template ON audit_pages (audit_id, template_key);
CREATE UNIQUE INDEX audit_pages_one_entry ON audit_pages (audit_id) WHERE is_entry;
```

`sample_kind='core'` sayfalar: ana sayfa, giriş URL'i, kullanıcı tanımlı URL'ler, şablon başına sabit temsilci (belge 00 §3.3). Çekirdek sayfa seçimi **sabit kuraldır**, tohuma bağlı değildir; keşif sayfaları `sample_seed` ile seçilir.

### 3.7 `page_fetches`

Belge 05 §6.5 sonucunun tablo karşılığıdır. Aynı sayfa için `page_raw` ve `page_rendered` ayrı satırlardır (`js_gap` bunların farkıdır).

```sql
CREATE TABLE page_fetches (
  id               uuid PRIMARY KEY,
  tenant_id        uuid        NOT NULL,
  audit_id         uuid        NOT NULL,
  page_id          uuid,                            -- robots/sitemap/tls için NULL
  kind             text        NOT NULL CHECK (kind IN
                     ('page_raw','page_rendered','robots','sitemap','transport')),
  requested_url    text        NOT NULL,
  final_url        text,
  status           integer,                         -- HTTP durum kodu
  redirect_chain   jsonb       NOT NULL DEFAULT '[]',   -- [{url,status}] (belge 05 §6.4)
  headers          jsonb       NOT NULL DEFAULT '{}',   -- yalnız izinli başlıklar (§6.3)
  html_bytes       bigint,
  content_encoding text,
  timing           jsonb,                           -- {ttfb_ms,total_ms}
  mode_used        text        CHECK (mode_used IN ('raw','rendered')),
  is_spa           boolean,
  js_gap           jsonb,                           -- yalnız page_rendered; belge 05 §7.2 alanları
  truncated        boolean     NOT NULL DEFAULT false,
  error            jsonb,                           -- {code, message}
  body_ref         text,                            -- nesne anahtarı (§6.1); NULL = silindi/yok
  body_sha256      text,                            -- bütünlük + önbellek içerik_hash girdisi
  body_size        bigint,
  body_compression text        CHECK (body_compression IN ('zstd','gzip','none')),
  body_expires_at  timestamptz,
  body_deleted_at  timestamptz,
  fetched_at       timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, audit_id) REFERENCES audits (tenant_id, id),
  FOREIGN KEY (tenant_id, page_id)  REFERENCES audit_pages (tenant_id, id),
  CHECK ((kind IN ('page_raw','page_rendered')) = (page_id IS NOT NULL))
);
CREATE INDEX page_fetches_audit ON page_fetches (audit_id, kind);
CREATE UNIQUE INDEX page_fetches_page_kind ON page_fetches (page_id, kind)
  WHERE kind IN ('page_raw','page_rendered');
CREATE INDEX page_fetches_expiry ON page_fetches (body_expires_at)
  WHERE body_ref IS NOT NULL;
```

Alan adları `fetch_page.py` sonucuyla uyumludur (`url`, `status_code`, `headers`, `redirect_chain`, `ttfb_ms`, `response_time_ms`, `content_bytes`, `error`) `[doğrulandı: 02 §6.5]`; bizde `status` ve `timing` olarak adlandırılır. `mode_used` `render_page` çıktısından gelir `[K]`.

### 3.8 `findings`

Belge 01 §6 JSON'unun tablo karşılığı. **Değiştirilemez.** `recommendation`, `effort`, `impact` bu tabloda **yoktur**: Katman C çıktısı `finding_advice` tablosundadır (V6, §3.9). Belge 01 §6'daki JSON'da bu üç alan bulgu içinde görünür; rapor üretiminde (§7.1) iki tablo birleştirilir.

```sql
CREATE TABLE findings (
  id                uuid PRIMARY KEY,
  tenant_id         uuid        NOT NULL,
  audit_id          uuid        NOT NULL,
  page_id           uuid,                              -- scope='site' ise NULL olabilir
  check_id          text        NOT NULL,              -- 'canonical-points-elsewhere'
  rule_version      text        NOT NULL REFERENCES rule_versions(version),
  category          text        NOT NULL CHECK (category IN
                      ('technical','onpage','content','schema','performance','ai_readiness','images')),
  layer             text        NOT NULL CHECK (layer IN ('A','B')),   -- C bulgu üretmez; öneri üretir
  severity          text        NOT NULL CHECK (severity IN ('Critical','High','Medium','Low','Info')),
  severity_original text        NOT NULL CHECK (severity_original IN ('Critical','High','Medium','Low','Info')),
  severity_reason   text,
  scope             text        NOT NULL CHECK (scope IN ('page','site')),
  url               text,
  message           text        NOT NULL,              -- sabit metin, sayfa verisi içermez
  evidence          text,                              -- ≤ 200 karakter, güvenilmeyen (belge 01 §6)
  count             integer     CHECK (count >= 0),
  heuristic         boolean     NOT NULL DEFAULT false,
  confidence        text        NOT NULL CHECK (confidence IN ('high','medium','low')),
  fingerprint       text        NOT NULL,              -- sha256(check_id|scope|url_match_key) trend/diff için
  created_at        timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, audit_id) REFERENCES audits (tenant_id, id),
  FOREIGN KEY (tenant_id, page_id)  REFERENCES audit_pages (tenant_id, id),
  UNIQUE (tenant_id, id),
  CHECK (severity = severity_original OR severity_reason IS NOT NULL),
  CHECK (char_length(evidence) <= 200),
  CHECK (scope = 'site' OR page_id IS NOT NULL)
);
CREATE INDEX findings_audit_cat   ON findings (audit_id, category, severity);
CREATE INDEX findings_audit_check ON findings (audit_id, check_id);
CREATE INDEX findings_page        ON findings (page_id) WHERE page_id IS NOT NULL;
CREATE INDEX findings_fingerprint ON findings (tenant_id, fingerprint);
```

`layer` yalnız `A`/`B`'dir: Katman C bulgu üretmez, mevcut bulguya öneri ekler veya danışma skoru üretir (belge 01 §4). Sözleşmedeki `layer` enum'u `A|B|C` olduğundan `CHECK` bilinçli olarak daha dar tutulmuştur, bkz. §11 DM10.

`UNIQUE (tenant_id, id)` ve `evidence` boyut `CHECK`'i, belge 01 P7 (sayfa içeriği güvenilmez, kırpılır) ilkesinin veritabanı yüzüdür.

### 3.9 `finding_advice` (ek tablo, Faz 2)

```sql
CREATE TABLE finding_advice (
  id              uuid PRIMARY KEY,
  tenant_id       uuid        NOT NULL,
  audit_id        uuid        NOT NULL,
  finding_id      uuid        NOT NULL,
  recommendation  text        NOT NULL,
  effort          text        CHECK (effort IN ('low','medium','high')),
  impact          text        CHECK (impact IN ('low','medium','high')),
  llm_call_id     uuid        NOT NULL,
  rubric_version  text        NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, audit_id)   REFERENCES audits (tenant_id, id),
  FOREIGN KEY (tenant_id, finding_id) REFERENCES findings (tenant_id, id),
  UNIQUE (finding_id, rubric_version)
);
```

Öneri yeniden üretilirse (`rubric_version` değişir) **yeni satır** eklenir; rapor en yeni sürümü gösterir.

### 3.10 `not_checked`

Reason kodları belge 05 §12 ile aynıdır. Aynı kodlardan bazıları (`tls-handshake-failed`, `robots-disallows-entry`, `status-error`) aynı zamanda bulgudur; `not_checked` yalnız "bu kontrol **çalıştırılamadı**" kaydıdır.

```sql
CREATE TABLE not_checked (
  id           uuid PRIMARY KEY,
  tenant_id    uuid        NOT NULL,
  audit_id     uuid        NOT NULL,
  page_id      uuid,
  check_id     text        NOT NULL,
  reason_code  text        NOT NULL CHECK (reason_code IN
                 ('target-rejected','unreachable','tls-handshake-failed','status-error',
                  'robots-unreachable','robots-disallows-entry','sitemap-missing','sitemap-invalid',
                  'headers-unavailable','render-failed','psi-unavailable','language-unsupported',
                  'partial-sample','words-not-measurable')),
  detail       text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, audit_id) REFERENCES audits (tenant_id, id),
  FOREIGN KEY (tenant_id, page_id)  REFERENCES audit_pages (tenant_id, id)
);
CREATE INDEX not_checked_audit ON not_checked (audit_id, check_id);
CREATE UNIQUE INDEX not_checked_uq
  ON not_checked (audit_id, check_id, COALESCE(page_id, '00000000-0000-0000-0000-000000000000'::uuid));
```

Yeni reason kodu eklemek bir Alembic göçüdür (`CHECK` değiştirilir, §9). Kod listesi belge 05 §12 ile **birlikte** güncellenir.

### 3.11 `page_scores`

Sayfa düzeyi skorlar: P25 dağılımı (belge 01 §9) ve çekirdek sayfa trendi için gerekir. Sözleşmedeki tablo listesinde yoktur; **ek tablo** (§11 DM11).

```sql
CREATE TABLE page_scores (
  id              uuid PRIMARY KEY,
  tenant_id       uuid        NOT NULL,
  audit_id        uuid        NOT NULL,
  page_id         uuid        NOT NULL,
  score_version   text        NOT NULL REFERENCES score_versions(version),
  overall         numeric(5,2),                       -- NULL = bu sayfa için ölçülen kategori yok
  categories      jsonb       NOT NULL,               -- {"technical":62.0,"onpage":80.0,...}; ölçülmeyen yok
  measured_weight numeric(5,2) NOT NULL,              -- §8.2 'kapsam' sayfa düzeyi
  created_at      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, audit_id) REFERENCES audits (tenant_id, id),
  FOREIGN KEY (tenant_id, page_id)  REFERENCES audit_pages (tenant_id, id),
  UNIQUE (page_id, score_version)
);
CREATE INDEX page_scores_audit ON page_scores (audit_id, score_version);
```

### 3.12 `category_scores`

Belge 01 §8.1: kategori skoru, ceza dökümü, ağırlık ve yeniden normalize ağırlık. `basis` üç değer alır: `all` (çekirdek + keşif sayfaları), `core` (yalnız çekirdek, **trend tabanı**), `page` (tek sayfa, sayfa modu kartı veya sayfa düzeyi).

```sql
CREATE TABLE category_scores (
  id                uuid PRIMARY KEY,
  tenant_id         uuid        NOT NULL,
  audit_id          uuid        NOT NULL,
  score_version     text        NOT NULL REFERENCES score_versions(version),
  category          text        NOT NULL CHECK (category IN
                      ('technical','onpage','content','schema','performance','ai_readiness','images')),
  basis             text        NOT NULL CHECK (basis IN ('all','core','page')),
  page_id           uuid,
  weight            numeric(5,2) NOT NULL,            -- w(c), profil ağırlığı
  weight_normalized numeric(6,5),                     -- ağırlık'(c); ölçülmediyse NULL
  measured          boolean     NOT NULL,
  score             numeric(5,2),                     -- ölçülmediyse NULL
  raw_penalty       numeric(6,2),
  confidence        text        CHECK (confidence IN ('high','medium','low')),
  reason_code       text,                             -- measured=false ise not_checked kodu
  penalties         jsonb       NOT NULL DEFAULT '[]',-- [{check_id,severity,points,kapsam,pages}]
  created_at        timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, audit_id) REFERENCES audits (tenant_id, id),
  FOREIGN KEY (tenant_id, page_id)  REFERENCES audit_pages (tenant_id, id),
  CHECK (measured = (score IS NOT NULL)),
  CHECK ((basis = 'page') = (page_id IS NOT NULL)),
  CHECK (measured OR reason_code IS NOT NULL)
);
CREATE UNIQUE INDEX category_scores_agg_uq
  ON category_scores (audit_id, score_version, category, basis) WHERE page_id IS NULL;
CREATE UNIQUE INDEX category_scores_page_uq
  ON category_scores (page_id, score_version, category) WHERE page_id IS NOT NULL;
```

### 3.13 `audit_scores`

Genel skor, kapsam, kapı ve güven (belge 01 §8.2-8.5). **Her `score_version` için bir satır**: yeniden hesap aynı denetime yeni satır ekler (§4.3).

```sql
CREATE TABLE audit_scores (
  id                 uuid PRIMARY KEY,
  tenant_id          uuid        NOT NULL,
  audit_id           uuid        NOT NULL,
  score_version      text        NOT NULL REFERENCES score_versions(version),
  overall            numeric(5,2),                    -- NULL = yetersiz veri
  raw_overall        numeric(5,2),                    -- kapıdan önce
  coverage           numeric(5,2) NOT NULL,           -- Σ ölçülen w(c), 0-100
  insufficient_data  boolean     NOT NULL,
  gate               jsonb,                           -- {id, cap}
  confidence         text        NOT NULL CHECK (confidence IN ('high','medium','low')),
  trend_score        numeric(5,2),                    -- yalnız basis='core'
  trend_pages        integer,
  p25_page_score     numeric(5,2),
  page_score_dist    jsonb,                           -- {n,p10,p25,p50,p75,p90}
  computed_at        timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, audit_id) REFERENCES audits (tenant_id, id),
  UNIQUE (audit_id, score_version),
  CHECK (insufficient_data = (overall IS NULL)),
  CHECK (overall IS NULL OR raw_overall IS NOT NULL)
);
```

Kapsam eşiği (60, belge 01 D2) DB'ye yazılmaz: `score_versions.config` içindedir; veritabanı yalnız tutarlılığı (`insufficient_data ⇔ overall IS NULL`) zorlar.

### 3.13a `page_extracts` (Faz 2b)

Katman C'nin **çıkarılmış girdisi** (belge 03 §4.2 `ContentInput`). Üç amaç taşır: (1) Katman C yeniden çalıştırma ve Q&A'nın **yeniden fetch yapmadan** çalışması (belge 00 §3.2, IO4); (2) önbellek anahtarının `content_hash` girdisi; (3) kanıt (alıntı) doğrulamasının aynı metne karşı tekrarlanabilmesi. Ham HTML burada **değildir** (belge 05 §5.4).

```sql
CREATE TABLE page_extracts (
  id             uuid PRIMARY KEY,
  tenant_id      uuid        NOT NULL,
  audit_id       uuid        NOT NULL,
  page_id        uuid        NOT NULL,
  schema_version text        NOT NULL,                -- ContentInput şeması sürümü
  content_hash   text        NOT NULL,                -- sha256(normalize(girdi_alanları)); llm_cache anahtarının parçası
  input          jsonb       NOT NULL,                -- {facts, untrusted:{title,h1,outline,main_text,byline,chrome_links}}, üst sınırlı
  size_bytes     integer     NOT NULL CHECK (size_bytes <= 65536),
  expires_at     timestamptz NOT NULL,                -- 30 gün (IO4); sonra satır silinir, API 409 snapshot-expired döner
  created_at     timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, audit_id) REFERENCES audits (tenant_id, id),
  FOREIGN KEY (tenant_id, page_id)  REFERENCES audit_pages (tenant_id, id),
  UNIQUE (tenant_id, page_id, content_hash)
);
CREATE INDEX page_extracts_expiry ON page_extracts (expires_at);
```

`input.untrusted.*` sayfadan geldiği için **güvenilmeyen** etiketlidir; yalnız LLM worker'ı ve Report/Q&A bağlam kurucusu okur. Kişisel veri riski DM5 kapsamındadır (kırpma ve maskeleme).

### 3.14 `advisory_scores` (Faz 2)

Danışma skorları (E-E-A-T, SXO) **genel skora girmez**, ayrı tabloda (belge 01 §4, karar D3).

```sql
CREATE TABLE advisory_scores (
  id             uuid PRIMARY KEY,
  tenant_id      uuid        NOT NULL,
  audit_id       uuid        NOT NULL,
  page_id        uuid,
  kind           text        NOT NULL CHECK (kind IN ('eeat','ai_readiness','sxo')),
  score          numeric(5,2),                         -- NULL: kapsam < 50 veya yalnız yorum (ai_readiness). Sayıyı KOD hesaplar (belge 03 §3.3)
  label          text        CHECK (label IN ('exceptional','strong','moderate','weak','very_low')),  -- 90-100/70-89/50-69/30-49/0-29
  coverage_pct   numeric(5,2),                         -- değerlendirilen faktör ağırlığı (belge 03 §3.3)
  factors        jsonb       NOT NULL DEFAULT '[]',    -- [{factor, band, value, r, assessed, not_assessed_reason}]
  signals        jsonb       NOT NULL DEFAULT '[]',    -- [{signal_id, status, field, quote}]  (quote <= 200 karakter, doğrulanmış; DM5)
  observations   jsonb       NOT NULL DEFAULT '[]',    -- doğrulanmış gözlemler (belge 03 §5.5)
  method         text        NOT NULL,                 -- 'llm-signals+code-bands'
  confidence     text        NOT NULL CHECK (confidence IN ('high','medium','low')),
  rubric_version text        NOT NULL,
  prompt_version text        NOT NULL,
  input_hash     text        NOT NULL,                 -- page_extracts.content_hash
  llm_call_id    uuid        NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, audit_id) REFERENCES audits (tenant_id, id),
  FOREIGN KEY (tenant_id, page_id)  REFERENCES audit_pages (tenant_id, id),
  CHECK ((score IS NULL) = (label IS NULL)),
  CHECK (kind <> 'ai_readiness' OR score IS NULL)      -- AI hazırlık yorumu skorsuzdur (belge 03 §6)
);
CREATE INDEX advisory_scores_audit ON advisory_scores (audit_id, kind);
```

### 3.15 `llm_calls`, `llm_cache` (Faz 2)

```sql
CREATE TABLE llm_calls (
  id             uuid PRIMARY KEY,
  tenant_id      uuid        NOT NULL,
  audit_id       uuid,
  page_id        uuid,
  purpose        text        NOT NULL CHECK (purpose IN ('eeat','ai_readiness','sxo','synthesize','qa')),   -- belge 03 modülleri
  model_id       text        NOT NULL,
  key_source     text        NOT NULL CHECK (key_source IN ('platform','byok')),
  byok_key_id    uuid,
  rubric_version text,
  prompt_version text,
  prompt_sha256  text        NOT NULL,                -- ham prompt DB'de yok (§6)
  input_tokens   integer,
  output_tokens  integer,
  cost_usd       numeric(10,6),
  latency_ms     integer,
  status         text        NOT NULL CHECK (status IN ('ok','error','cache_hit','budget_stop','schema_invalid')),
  cache_key      text,
  payload_ref    text,                                -- redakte edilmiş istek/yanıt, nesne depolama
  error          jsonb,
  created_at     timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, audit_id) REFERENCES audits (tenant_id, id),
  FOREIGN KEY (tenant_id, page_id)  REFERENCES audit_pages (tenant_id, id),
  UNIQUE (tenant_id, id),
  CHECK ((key_source = 'byok') = (byok_key_id IS NOT NULL))
);
CREATE INDEX llm_calls_tenant_time ON llm_calls (tenant_id, created_at DESC);
CREATE INDEX llm_calls_audit       ON llm_calls (audit_id);

CREATE TABLE llm_cache (
  tenant_id      uuid        NOT NULL REFERENCES tenants(id),
  cache_key      text        NOT NULL,                -- sha256(içerik_hash | rubrik_sürümü | model_id)
  purpose        text        NOT NULL,
  content_hash   text        NOT NULL,
  rubric_version text        NOT NULL,
  model_id       text        NOT NULL,
  response       jsonb       NOT NULL,                -- JSON Schema ile doğrulanmış yapılandırılmış çıktı
  origin_call_id uuid        NOT NULL,
  hit_count      integer     NOT NULL DEFAULT 0,
  created_at     timestamptz NOT NULL DEFAULT now(),
  expires_at     timestamptz,
  PRIMARY KEY (tenant_id, cache_key)
);
```

Önbellek anahtarı belge 01 §4.1'deki üçlüdür. **Kiracı başına** tutulur (kiracılar arası paylaşım `[?]` DM2).

### 3.16 `reports`

```sql
CREATE TABLE reports (
  id             uuid PRIMARY KEY,
  tenant_id      uuid        NOT NULL,
  audit_id       uuid        NOT NULL,
  format         text        NOT NULL CHECK (format IN ('json','html','pdf')),
  schema_version text        NOT NULL,                -- rapor JSON şeması sürümü (belge 06)
  score_version  text        NOT NULL REFERENCES score_versions(version),
  body_ref       text        NOT NULL,
  body_sha256    text        NOT NULL,
  body_size      bigint      NOT NULL,
  generated_at   timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, audit_id) REFERENCES audits (tenant_id, id),
  UNIQUE (audit_id, format, schema_version, score_version)
);
```

JSON rapor **anlık görüntü** olarak saklanır: skor ve bulgular değişmez olsa da `finding_advice` yeni sürümle eklenebilir; kullanıcının indirdiği/paylaştığı rapor sabit kalmalıdır `[B]`. PDF ve HTML aynı JSON'dan üretilir (belge 08 §14 çıkarımı).

### 3.17 `qa_threads`, `qa_messages` (Faz 2)

Belge 00 §3.2: cevaplar yalnız kayıtlı rapordan gelir, bulgu id'sine atıf zorunludur.

```sql
CREATE TABLE qa_threads (
  id          uuid PRIMARY KEY,
  tenant_id   uuid        NOT NULL,
  audit_id    uuid        NOT NULL,
  user_id     uuid        NOT NULL,
  status      text        NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, audit_id) REFERENCES audits (tenant_id, id),
  FOREIGN KEY (tenant_id, user_id)  REFERENCES users  (tenant_id, id),
  UNIQUE (tenant_id, id)
);

CREATE TABLE qa_messages (
  id               uuid PRIMARY KEY,
  tenant_id        uuid        NOT NULL,
  thread_id        uuid        NOT NULL,
  role             text        NOT NULL CHECK (role IN ('user','assistant')),
  content          text        NOT NULL,
  citations        jsonb       NOT NULL DEFAULT '[]',   -- [{"finding_id":"...","url":"..."}]
  refused          boolean     NOT NULL DEFAULT false,
  refusal_reason   text        CHECK (refusal_reason IN ('not_in_report','out_of_scope','budget','unsafe')),
  llm_call_id      uuid,
  created_at       timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, thread_id) REFERENCES qa_threads (tenant_id, id),
  CHECK (role = 'user'
         OR refused
         OR jsonb_array_length(citations) > 0),        -- atıfsız asistan cevabı yok
  CHECK (NOT refused OR refusal_reason IS NOT NULL)
);
CREATE INDEX qa_messages_thread ON qa_messages (thread_id, created_at);
```

`citations` içindeki `finding_id` değerlerinin **o denetime ait** olduğu uygulamada doğrulanır (JSONB içinde FK yoktur). Doğrulama başarısız olursa mesaj `refused=true, refusal_reason='not_in_report'` olarak kaydedilir.

### 3.18 `usage_ledger`

Kota ve maliyet için **ekleme-yalnız** defter (belge 00 §3.4, belge 05 §10). Bütçe kontrolü bu tabloyu toplar.

```sql
CREATE TABLE usage_ledger (
  id            uuid PRIMARY KEY,
  tenant_id     uuid        NOT NULL REFERENCES tenants(id),
  user_id       uuid,
  audit_id      uuid,
  kind          text        NOT NULL CHECK (kind IN
                  ('audit','page_fetch','render','llm_input_tokens','llm_output_tokens','qa_message','rerun')),
  quantity      numeric(14,3) NOT NULL CHECK (quantity >= 0),
  cost_usd      numeric(10,6),
  key_source    text        NOT NULL DEFAULT 'platform' CHECK (key_source IN ('platform','byok')),
  plan          text        NOT NULL,                  -- olay anındaki plan (geçici isimler)
  period_month  date        NOT NULL,                  -- ayın ilk günü, UTC
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX usage_ledger_period ON usage_ledger (tenant_id, period_month, kind);
```

`key_source='byok'` satırları **kotadan düşmez**, ama maliyet görünürlüğü için yazılır (belge 00 §3.4).

### 3.19 `byok_keys` (Faz 2)

```sql
CREATE TABLE byok_keys (
  id            uuid PRIMARY KEY,
  tenant_id     uuid        NOT NULL REFERENCES tenants(id),
  provider      text        NOT NULL CHECK (provider IN ('anthropic')),
  label         text        NOT NULL,
  last4         text        NOT NULL,                  -- ekranda gösterilen tek parça
  ciphertext    bytea       NOT NULL,                  -- DEK ile şifreli anahtar
  wrapped_dek   bytea       NOT NULL,                  -- KMS/KEK ile sarılmış DEK
  kms_key_id    text        NOT NULL,
  status        text        NOT NULL DEFAULT 'active' CHECK (status IN ('active','invalid','revoked')),
  created_by    uuid,
  created_at    timestamptz NOT NULL DEFAULT now(),
  last_used_at  timestamptz,
  revoked_at    timestamptz,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, created_by) REFERENCES users (tenant_id, id)
);
ALTER TABLE llm_calls
  ADD FOREIGN KEY (tenant_id, byok_key_id) REFERENCES byok_keys (tenant_id, id);
```

Kurallar `[B]`:
- Anahtar yalnız **Katman C** çağrılarında çözülür (belge 00 §3.4); Katman A her zaman platformundur.
- Çözülmüş anahtar bellekte kısa süre tutulur; log, hata mesajı, `payload_ref` ve APM izine **yazılmaz**. Sızıntı testi (§9.4).
- Silme = `status='revoked'` + `ciphertext`/`wrapped_dek` sıfırlanır (rotasyon ve kullanıcı isteği).
- `ciphertext`/`wrapped_dek` kolonları API rolüne `SELECT` yetkisiyle verilmez, yalnız `byok_service` rolüne (§5.3).

### 3.20 Ek tablolar özeti

Sözleşmedeki listeye **eklenenler**: `finding_advice` (§3.9), `page_scores` (§3.11). Gerekçeler §11 DM10-DM11'de.

## 4. Değiştirilemezlik ve sürümleme

### 4.1 Hangi tablo ne kadar değişir

| Tablo | Değişim | Gerekçe |
|---|---|---|
| `audits`, `audit_stages`, `audit_pages` | **Yazılabilir** (iş akışı durumu) | Kuyruk/worker ilerlemesi |
| `page_fetches` | Ekleme-yalnız; yalnız `body_ref`, `body_deleted_at` retention işi tarafından güncellenir | Ham içerik saklama süresi |
| `findings`, `not_checked`, `page_scores`, `category_scores`, `audit_scores`, `advisory_scores`, `finding_advice`, `llm_calls`, `usage_ledger`, `reports` | **Ekleme-yalnız** | V1, V6 |
| `llm_cache` | `hit_count` güncellenir, içerik değişmez | |
| `page_extracts` | Ekleme-yalnız; satırlar **yalnız** retention işi tarafından `expires_at` sonrası silinir | IO4 saklama |
| `rule_versions`, `score_versions` | **Ekleme-yalnız**; yayımlanmış sürüm değişmez | V5 |
| `qa_messages` | Ekleme-yalnız | Denetlenebilirlik |

Zorlama: (1) uygulama rollerinden `UPDATE`/`DELETE` yetkisi kaldırılır; (2) **savunma derinliği** için tetikleyici (tablo sahibi yetkiyi atlatabilir):

```sql
CREATE FUNCTION forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' AND pg_has_role(current_user, 'retention_role', 'member') THEN
    RETURN OLD;                                   -- yalnız retention/silme işi
  END IF;
  RAISE EXCEPTION '% on % is not allowed (append-only)', TG_OP, TG_TABLE_NAME
    USING ERRCODE = '42501';
END $$;

-- findings için; diğer ekleme-yalnız tablolara aynı biçimde
CREATE TRIGGER findings_append_only
  BEFORE UPDATE OR DELETE ON findings
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- page_fetches: yalnız body_* kolonları değişebilir
CREATE FUNCTION page_fetches_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NOT pg_has_role(current_user, 'retention_role', 'member') THEN
      RAISE EXCEPTION 'page_fetches is append-only' USING ERRCODE = '42501';
    END IF;
    IF (to_jsonb(NEW) - 'body_ref' - 'body_deleted_at')
       IS DISTINCT FROM (to_jsonb(OLD) - 'body_ref' - 'body_deleted_at') THEN
      RAISE EXCEPTION 'only body_ref/body_deleted_at may change' USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
  ELSIF TG_OP = 'DELETE' THEN
    IF pg_has_role(current_user, 'retention_role', 'member') THEN RETURN OLD; END IF;
    RAISE EXCEPTION 'page_fetches is append-only' USING ERRCODE = '42501';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER page_fetches_guard_trg
  BEFORE UPDATE OR DELETE ON page_fetches
  FOR EACH ROW EXECUTE FUNCTION page_fetches_guard();
```

`ON DELETE CASCADE` kullanılmaz: silme, bağımlılık sırasıyla `retention_role` ile açıkça yapılır (§6.4). Böylece tetikleyici ve yetkiler tutarlı kalır.

### 4.2 Sürüm kayıtlarının içeriği

**`rule_versions.registry`**: belge 01 §5'teki `CheckDef` dizisinin anlık görüntüsü.

```json
[
  {"id":"noindex","category":"technical","layer":"A","scope":"page","severity":"Critical",
   "heuristic":false,"thresholds":{},"requires":["rendered"],"since":"1.0"},
  {"id":"title-too-long","category":"onpage","layer":"A","scope":"page","severity":"Medium",
   "heuristic":true,"thresholds":{"title_max_chars":60},"requires":[],"since":"1.0"}
]
```

Başlangıç içeriği: `page_checks.py` 47 kontrol (id, severity başlangıç değeri: Critical 2 / High 6 / Medium 24 / Low 15) `[doğrulandı]` + `transport_check` bulguları + site düzeyi kontroller (belge 01 §5.1).

**`score_versions.config`**: belge 01 §7-8'in sayısal parametreleri, kodda sabit değil **veri**.

```json
{
  "profiles": {"default": {"technical":25,"onpage":20,"content":20,"schema":10,
                           "performance":10,"ai_readiness":10,"images":5}},
  "active_profile": "default",
  "page_mode_categories": ["onpage","content","technical","schema","images"],
  "severity": {
    "Critical": {"base":40,"id_cap":40,"category_cap":100},
    "High":     {"base":15,"id_cap":15,"category_cap":60},
    "Medium":   {"base":6, "id_cap":6, "category_cap":30},
    "Low":      {"base":2, "id_cap":2, "category_cap":10},
    "Info":     {"base":0, "id_cap":0, "category_cap":0}
  },
  "coverage_rule": {"site_min":0.4,"site_slope":0.6,"count_min":0.5,"count_slope":0.5,"n_ref":20},
  "insufficient_data_below": 60,
  "gates": [
    {"cap":40,"when":["noindex","noindex-header","status>=400","tls-cert-expired",
                      "tls-cert-hostname-mismatch","tls-cert-not-trusted"]},
    {"cap":70,"when":["canonical-points-elsewhere","robots-blocks-site"]}
  ],
  "layer_b_adjust_max": 10
}
```

Değerler başlangıçtır, kalibrasyonla değişir (belge 01 §13.2). Her değişiklik **yeni `score_versions` satırıdır**; `config_sha256` bütünlüğü doğrular.

### 4.3 Yeniden hesap ve yeniden çalıştırma

| Durum | Ne yazılır | Eski veri |
|---|---|---|
| Ağırlık/formül değişti (`score_version` ↑), bulgular aynı | Aynı `audit_id` için yeni `page_scores`, `category_scores`, `audit_scores` satırları (yeni `score_version`) | Dokunulmaz. Eski sürüm sorgulanabilir |
| Kural değişti (`rule_version` ↑) | **Yeni denetim** (`parent_audit_id` dolu). HTML silindiyse yeniden fetch gerekir | Eski denetim değişmez |
| Modül yeniden çalıştırma (belge 00 §3.2) | Yeni denetim, `parent_audit_id` + `rerun_stages`; yalnız o aşamaların çıktıları yeniden üretilir | Eski denetim değişmez |
| Öneri yeniden üretimi | `finding_advice` yeni satır (`rubric_version`) | |

`audits.score_version` **kullanıcıya gösterilen birincil sürümdür**. Trend grafiği yalnız **aynı `score_version`**'lı skorları birleştirir (belge 01 §10).

## 5. Kiracı izolasyonu ve RLS

### 5.1 Katmanlar

1. **Bileşik FK** (§3): yanlış kiracı referansı oluşamaz.
2. **RLS**: her kiracı tablosunda `tenant_id = oturum kiracısı`.
3. **Roller**: uygulama, worker, retention, byok servisi, platform yöneticisi ayrı roller.
4. **Uygulama**: her istek/iş kiracı bağlamıyla açılır; bağlamsız sorgu satır döndürmez.

### 5.2 Politika

```sql
-- oturum kiracısı: işlem-yerel ayar; boş veya yoksa NULL -> hiçbir satır eşleşmez
CREATE FUNCTION app_tenant() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid $$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'users','sites','site_verifications','audits','audit_stages','audit_pages','page_fetches',
    'findings','finding_advice','not_checked','page_scores','category_scores','audit_scores',
    'advisory_scores','page_extracts','llm_calls','llm_cache','reports','qa_threads','qa_messages',
    'usage_ledger','byok_keys','monitoring_schedules','drift_baselines','drift_events'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format($f$CREATE POLICY tenant_isolation ON %I
                      USING (tenant_id = app_tenant())
                      WITH CHECK (tenant_id = app_tenant())$f$, t);
  END LOOP;
END $$;
```

`tenants` tablosunda politika `id = app_tenant()`'dir. `rule_versions`/`score_versions` global ve salt-okunurdur (RLS yok, uygulama rollerine yalnız `SELECT`).

`FORCE ROW LEVEL SECURITY`, tablo sahibinin de politikaya tabi olmasını sağlar; politikayı atlayacak tek rol `platform_admin` (`BYPASSRLS`) olur ve yalnız operasyon erişimi içindir.

### 5.3 Roller

| Rol | Yetki | Kullanan |
|---|---|---|
| `app_rw` | Kiracı tablolarında `SELECT/INSERT`; yalnız iş akışı tablolarında (`audits`, `audit_stages`, `audit_pages`, `qa_threads`, `sites`, `site_verifications`) `UPDATE`; `byok_keys.ciphertext/wrapped_dek` okuyamaz | FastAPI |
| `worker_rw` | `app_rw` + `page_fetches`/ölçüm tablolarına `INSERT` | Arq worker |
| `byok_service` | `byok_keys` şifreli kolonlarını okur; yalnız Katman C çağrı yolunda | LLM istemcisi |
| `retention_role` | Retention ve silme işleri için `DELETE`, `page_fetches` `body_*` `UPDATE` | zamanlı iş |
| `platform_admin` | `BYPASSRLS`, operasyon | insan, denetimli |
| `migrator` | Şema sahibi; uygulama çalışırken kullanılmaz | Alembic |

### 5.4 Oturum bağlamı

```python
# SQLAlchemy 2: her işlemin başında, işlem-yerel (is_local=true)
@event.listens_for(Session, "after_begin")
def _set_tenant(session, transaction, connection):
    tid = session.info.get("tenant_id")
    connection.exec_driver_sql(
        "SELECT set_config('app.tenant_id', %s, true)", (str(tid) if tid else "",)
    )
```

`is_local=true` yalnız işlem boyunca geçerlidir; havuzlanmış bağlantıda sızmaz. PgBouncer **işlem** havuzlamasıyla uyumu teoride sorunsuzdur, ancak **doğrulanmadı** (§10, prototiple test edilecek). Arq işleri `tenant_id`'yi iş yükünde taşır; worker her işte bağlamı açıkça kurar.

## 6. Nesne depolama, saklama ve silme

### 6.1 Anahtar düzeni

```
s3://<bucket>/
  t/{tenant_id}/a/{audit_id}/
     pages/{page_id}/raw.html.zst
     pages/{page_id}/rendered.html.zst
     site/robots.txt.zst
     site/sitemaps/{n}.xml.zst
     llm/{llm_call_id}.json.zst          # redakte edilmiş istek/yanıt, yalnız hata ayıklama
     reports/{report_id}.{json|html|pdf}
```

- Kiracı öneki **IAM koşuluyla** da zorlanır (iş yükü yalnız kendi önekine erişir) `[B]`.
- Sıkıştırma: `zstd` `[?]` (DM3; `gzip` yedek). `body_compression` kolonu kullanılan yöntemi saklar.
- `body_sha256`, **açık HTML'in** özetidir (sıkıştırma öncesi); önbellek `içerik_hash` girdisi olarak da kullanılır.

### 6.2 Saklama süreleri `[?]`

| Veri | Varsayılan | Not |
|---|---|---|
| `pages/*` (ham ve render HTML) | **30 gün** | `body_expires_at = fetched_at + 30d`; süre dolunca nesne silinir, `body_ref = NULL`, `body_deleted_at` dolar |
| `robots.txt`, sitemap | 30 gün | aynı |
| `llm/*` yükleri | 7 gün | yalnız hata ayıklama; kullanıcı verisi içerebilir |
| `reports/*` (JSON) | Süresiz (denetimle birlikte) | Paylaşılan raporun sabit kalması |
| Bulgu, skor, kapsam (DB) | Süresiz | Trend ve karşılaştırma |
| `usage_ledger` | Süresiz (muhasebe) | Hukuki saklama süreleri `[?]` |

Ham HTML silindikten sonra `rule_version` değişikliğinde **yeniden değerlendirme için yeniden fetch gerekir** (§4.3); ürün bunu açıkça söyler.

### 6.3 Başlık ve içerik minimizasyonu `[B]`

- `page_fetches.headers` **izinli listeyle** saklanır: `content-type`, `content-encoding`, `content-length`, `cache-control`, `x-robots-tag`, `link`, `strict-transport-security`, `content-security-policy`, `referrer-policy`, `permissions-policy`, `x-content-type-options`, `x-frame-options`, `server`, `location`. `Set-Cookie`, `Authorization` ve benzeri **asla** saklanmaz.
- Sorgu parametreleri maskelenir (`token`, `key`, `sig` vb. değerler `***`), kaynağın sitemap tarafındaki `_SECRET_PARAM` yaklaşımıyla aynı fikir `[K, doğrulandı: sitemap_discovery.py]`.
- `findings.evidence` ≤ 200 karakter `[K]`.

### 6.4 Silme akışı

1. **Retention işi (günlük):** `body_expires_at < now()` olan nesneleri siler → `page_fetches.body_ref = NULL, body_deleted_at = now()`. Aynı iş `page_extracts.expires_at < now()` satırlarını da siler.
2. **Denetim silme (kullanıcı isteği):** `retention_role` ile bağımlılık sırasıyla: `qa_messages → qa_threads → finding_advice → advisory_scores → page_extracts → llm_calls → reports → page_scores → category_scores → audit_scores → not_checked → findings → page_fetches → audit_pages → audit_stages → audits`; nesne öneki `t/{tenant}/a/{audit}/` silinir.
3. **Kiracı silme:** `tenants.status='deleting'`; yukarıdakiler tüm denetimler için, ardından `byok_keys` (anahtar materyali sıfırlanır), `sites`, `users`, `usage_ledger`, `tenants`. Nesne öneki `t/{tenant}/` silinir.

### 6.5 KVKK / GDPR notu `[?]`

Bu belge **hukuki görüş değildir**; ürün yayına çıkmadan hukuki inceleme gerekir. Veri envanteri:

| Veri | Kişisel veri olabilir mi | Önlem |
|---|---|---|
| `users.email` | Evet | Asgari alan; silme akışı (§6.4) |
| Ham HTML (`pages/*`) | Olabilir (yazar adı, e-posta, yorumlar) | 30 gün; kiracıya özel; erişim kısıtlı |
| `findings.evidence` | Olabilir (kırpılmış sayfa metni) | ≤ 200 karakter |
| LLM yükleri | Olabilir | Sayfa **ham HTML** modele verilmez, yalnız çıkarılmış alanlar (belge 05 §5.4); `llm/*` 7 gün |
| `byok_keys` | Sır (kişisel olmayabilir ama hassas) | Zarf şifreleme (V7) |

Açık hukuki sorular: veri konumu/aktarımı (LLM sağlayıcısı veri işleyen sıfatında mı), saklama süreleri, silme talebi SLA'sı, aydınlatma metni, tarama yapılan sitelerin üçüncü taraf verisi. Hepsi `[?]` ve belge 05/ayrı hukuki iş.

## 7. Örnek sorgular

### 7.1 Bir denetimin rapor JSON'unu üretme

Belge 01 §6 / `kaynak analizi notları 02` §15.6 rapor taslağının veritabanı karşılığı (belge 06 şemayı kesinleştirir). `:audit` ve `:sv` (score_version) parametredir.

```sql
SELECT jsonb_build_object(
  'score_version', s.score_version,
  'overall', jsonb_build_object(
      'score', s.overall, 'coverage', s.coverage, 'gate', s.gate,
      'confidence', s.confidence, 'insufficient_data', s.insufficient_data),
  'categories', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
          'id', c.category, 'weight', c.weight, 'measured', c.measured,
          'score', c.score, 'reason', c.reason_code, 'penalties', c.penalties)
          ORDER BY c.category), '[]')
      FROM category_scores c
      WHERE c.audit_id = a.id AND c.score_version = s.score_version
        AND c.basis = 'all' AND c.page_id IS NULL),
  'advisory', (
      SELECT coalesce(jsonb_object_agg(x.kind, jsonb_build_object(
          'score', x.score, 'band', x.band, 'method', x.method, 'confidence', x.confidence)), '{}')
      FROM advisory_scores x WHERE x.audit_id = a.id AND x.page_id IS NULL),
  'findings', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
          'id', f.check_id, 'rule_version', f.rule_version, 'category', f.category,
          'layer', f.layer, 'severity', f.severity, 'scope', f.scope, 'url', f.url,
          'message', f.message, 'evidence', f.evidence, 'count', f.count,
          'heuristic', f.heuristic, 'confidence', f.confidence,
          'recommendation', fa.recommendation, 'effort', fa.effort, 'impact', fa.impact)
          ORDER BY CASE f.severity WHEN 'Critical' THEN 0 WHEN 'High' THEN 1
                                   WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END, f.check_id), '[]')
      FROM findings f
      LEFT JOIN LATERAL (
         SELECT recommendation, effort, impact FROM finding_advice
         WHERE finding_id = f.id ORDER BY created_at DESC LIMIT 1) fa ON true
      WHERE f.audit_id = a.id),
  'not_checked', (
      SELECT coalesce(jsonb_agg(jsonb_build_object('id', n.check_id, 'reason', n.reason_code)), '[]')
      FROM not_checked n WHERE n.audit_id = a.id),
  'coverage', a.coverage
) AS report
FROM audits a
JOIN audit_scores s ON s.audit_id = a.id AND s.score_version = :sv
WHERE a.id = :audit;
```

RLS açıkken `WHERE tenant_id = ...` yazmak gerekmez; bağlam `set_config` ile gelir.

### 7.2 Trend: yalnız çekirdek sayfa skoru

Belge 00 §3.3: trend skoru **çekirdek örneklemden** gelir ve **aynı `score_version`** ile karşılaştırılır.

```sql
SELECT a.finished_at, s.trend_score, s.trend_pages, s.score_version
FROM audits a
JOIN audit_scores s ON s.audit_id = a.id AND s.score_version = a.score_version
WHERE a.site_id = :site
  AND a.status IN ('completed','partial')
  AND s.trend_score IS NOT NULL
  AND s.score_version = :sv                       -- sürümler karıştırılmaz (belge 01 §10)
ORDER BY a.finished_at;

-- Tek bir çekirdek sayfanın zaman içi skoru
SELECT a.finished_at, ps.overall
FROM audit_pages p
JOIN audits a        ON a.id = p.audit_id
JOIN page_scores ps  ON ps.page_id = p.id AND ps.score_version = :sv
WHERE a.site_id = :site AND p.sample_kind = 'core' AND p.url_match_key = :key
ORDER BY a.finished_at;
```

### 7.3 `kapsam(f)` için: aynı id'li bulguların sayfa oranı

Belge 01 §8.1: site düzeyi `kapsam = min(1, 0.4 + 0.6 × etkilenen_sayfa_oranı)`; sayfa içi sayımda `0.5 + 0.5 × log10(1+count)/log10(1+N_ref)`.

```sql
WITH fetched AS (
  SELECT count(*)::numeric AS n
  FROM audit_pages
  WHERE audit_id = :audit AND fetch_state = 'fetched'
    AND (:basis = 'all' OR sample_kind = 'core')
),
aff AS (
  SELECT f.check_id, f.severity,
         count(DISTINCT f.page_id)       AS pages,
         coalesce(sum(f.count), 0)       AS total_count
  FROM findings f
  JOIN audit_pages p ON p.id = f.page_id
  WHERE f.audit_id = :audit AND f.scope = 'page'
    AND (:basis = 'all' OR p.sample_kind = 'core')
  GROUP BY f.check_id, f.severity
)
SELECT a.check_id, a.severity, a.pages,
       LEAST(1, 0.4 + 0.6 * a.pages / NULLIF(fetched.n, 0))               AS kapsam_site,
       LEAST(1, 0.5 + 0.5 * log(1 + a.total_count) / log(1 + 20))          AS kapsam_count   -- log() = 10 tabanı
FROM aff a CROSS JOIN fetched;
```

Formül sabitleri (`0.4`, `0.6`, `20`) `score_versions.config.coverage_rule`'dan gelir; sorgu örnektir, üretimde skorlayıcı (Python) hesaplar ve bu sorgu **doğrulama/rapor** içindir `[B]`.

### 7.4 Önbellek ve bütçe

```sql
-- Önbellek denemesi
UPDATE llm_cache SET hit_count = hit_count + 1
WHERE tenant_id = :tenant AND cache_key = :key AND (expires_at IS NULL OR expires_at > now())
RETURNING response;

-- Bu ay platform kotasından kullanılan LLM token
SELECT coalesce(sum(quantity), 0)
FROM usage_ledger
WHERE tenant_id = :tenant AND period_month = date_trunc('month', now())::date
  AND kind IN ('llm_input_tokens','llm_output_tokens') AND key_source = 'platform';
```

`llm_cache` güncellemesi `hit_count` ile sınırlıdır (§4.1); `UPDATE` yetkisi bu tabloda yalnız `hit_count` için tanımlanır (kolon düzeyi `GRANT`).

## 8. Faz 3 tabloları (izleme ve drift)

### 8.1 Hangi fazda hangi tablo

Yol haritası belge 09 ve 00'daki fazlarla uyumludur (Faz 0 temel, 1 deterministik çekirdek, 2 veri ve LLM, 3 genişleme).

| Faz | Tablolar |
|---|---|
| **0** Temel | `tenants`, `users`, `sites`, `audits`, `audit_stages`, `audit_pages`, `page_fetches`, `findings`, `not_checked`, `rule_versions`, `score_versions` |
| **1** Deterministik çekirdek | `page_scores`, `category_scores`, `audit_scores`, `reports` (HTML/JSON), `usage_ledger` |
| **2** Veri + LLM + sahiplik | `llm_calls`, `llm_cache`, `page_extracts`, `advisory_scores`, `finding_advice`, `qa_threads`, `qa_messages`, `byok_keys`, `site_verifications` |
| **3** Genişleme | `monitoring_schedules`, `drift_baselines`, `drift_events` (+ PDF `reports` biçimi) |

`sites.tier` Faz 0'dan itibaren vardır (`unverified` sabit); doğrulama Faz 2'de gelir.

### 8.2 DDL

kaynak proje drift'i tek kullanıcılı yerel SQLite'tır (§10). Biz bunu kiracılı ve denetimle bağlı hale getiririz:

```sql
CREATE TABLE monitoring_schedules (
  id                 uuid PRIMARY KEY,
  tenant_id          uuid        NOT NULL,
  site_id            uuid        NOT NULL,
  mode               text        NOT NULL CHECK (mode IN ('site','page')),
  cadence            text        NOT NULL CHECK (cadence IN ('daily','weekly','monthly')),
  core_urls          jsonb       NOT NULL DEFAULT '[]',     -- kullanıcı tanımlı çekirdek URL'ler (belge 00 §3.3)
  exploration        boolean     NOT NULL DEFAULT true,     -- dönen keşif örneklemi
  status             text        NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','deleted')),
  next_run_at        timestamptz NOT NULL,
  last_audit_id      uuid,
  created_by         uuid,
  created_at         timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, site_id)       REFERENCES sites  (tenant_id, id),
  FOREIGN KEY (tenant_id, last_audit_id) REFERENCES audits (tenant_id, id),
  UNIQUE (tenant_id, id)
);
CREATE INDEX monitoring_due ON monitoring_schedules (next_run_at) WHERE status = 'active';

CREATE TABLE drift_baselines (
  id              uuid PRIMARY KEY,
  tenant_id       uuid        NOT NULL,
  site_id         uuid        NOT NULL,
  audit_id        uuid        NOT NULL,                     -- baseline'ın alındığı denetim
  page_id         uuid        NOT NULL,
  url_match_key   text        NOT NULL,
  captured_at     timestamptz NOT NULL DEFAULT now(),
  is_active       boolean     NOT NULL DEFAULT true,
  status_code     integer,
  title           text,
  meta_description text,
  canonical       text,
  robots          text,
  h1              text,
  h2              jsonb,
  h3              jsonb,
  schema_data     jsonb,
  og              jsonb,
  cwv             jsonb,
  html_hash       text,
  schema_hash     text,
  FOREIGN KEY (tenant_id, site_id)  REFERENCES sites (tenant_id, id),
  FOREIGN KEY (tenant_id, audit_id) REFERENCES audits (tenant_id, id),
  FOREIGN KEY (tenant_id, page_id)  REFERENCES audit_pages (tenant_id, id),
  UNIQUE (tenant_id, id)
);
CREATE UNIQUE INDEX drift_baseline_active
  ON drift_baselines (site_id, url_match_key) WHERE is_active;

CREATE TABLE drift_events (
  id           uuid PRIMARY KEY,
  tenant_id    uuid        NOT NULL,
  site_id      uuid        NOT NULL,
  baseline_id  uuid        NOT NULL,
  audit_id     uuid        NOT NULL,
  url_match_key text       NOT NULL,
  rule_id      text        NOT NULL,                        -- 'noindex_added', 'title_changed' ...
  drift_severity text      NOT NULL CHECK (drift_severity IN ('CRITICAL','WARNING','INFO')),
  old_value    text,
  new_value    text,
  detail       text,
  detected_at  timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, baseline_id) REFERENCES drift_baselines (tenant_id, id),
  FOREIGN KEY (tenant_id, audit_id)    REFERENCES audits (tenant_id, id)
);
CREATE INDEX drift_events_site ON drift_events (site_id, detected_at DESC);
```

Notlar:
- `drift_severity` (`CRITICAL/WARNING/INFO`), kaynaktaki 17 kuralın sözlüğüdür (8/6/3) `[doğrulandı]` ve **bulgu severity'sinden (`Critical/High/…`) ayrı tutulur**: drift skoru etkilemez (belge 01 §10).
- Kaynak, bir karşılaştırma sonucunu tek bir `results_json` blob'u olarak saklar; biz **yalnız tetiklenen kuralları satır olarak** yazarız (sorgulanabilir, uyarı akışına uygun). Tetiklenmeyen ve atlanan kurallar `audits.coverage`/audit çıktısında özetlenir `[B]`.
- `drift_baselines` Faz 3'te `audit_pages`'e bağlıdır; HTML silinse bile baseline alanları ve `html_hash` kalır (karşılaştırma için yeterli).
- Baseline'a bir **çekirdek** sayfa girer; keşif sayfaları baseline almaz (trend ve drift aynı çekirdek kümesine dayanır).

## 9. Göç (Alembic) stratejisi

### 9.1 Yapı ve sıra

- Tek `alembic/versions/` zinciri; **her faz bir göç grubudur**: `0001_phase0_core`, `0002_phase1_scoring`, `0003_phase2_llm_qa_byok`, `0004_phase3_monitoring`. Faz içindeki ek değişiklikler ayrı revizyondur.
- Şema sahibi `migrator` rolüdür; uygulama rolleri yetkileri göçle alır (`GRANT/REVOKE` göç içindedir, elle değil).
- Tetikleyiciler, politikalar ve fonksiyonlar (`forbid_mutation`, `app_tenant`, RLS) göçle gelir; `alembic check` gibi bir kapı bunların varlığını test eder (§9.4).

### 9.2 Genişlet-daralt (expand/contract) `[B]`

1. **Genişlet:** yeni kolon/tablo `NULL`able veya `DEFAULT` ile eklenir; eski kod çalışmaya devam eder.
2. **Uygulamayı geçir:** yeni sürüm hem eskiyi hem yeniyi okur/yazar.
3. **Daralt:** eski kolon sonraki sürümde, geriye dönüş penceresi geçince kaldırılır.
- Aynı sürümde yıkıcı değişiklik yapılmaz. `NOT NULL` eklemek: önce `CHECK (col IS NOT NULL) NOT VALID`, doldurma, `VALIDATE CONSTRAINT`, sonra `SET NOT NULL`.
- **Enum değeri eklemek:** `CHECK` kısıtını bırakıp daha geniş olanı `NOT VALID` olarak eklemek, ardından `VALIDATE` (V4). Yeni `reason_code`, `stage`, `kind` değerleri bu yolla gelir.

### 9.3 Veri göçleri ve tohum veri

- `rule_versions` ve `score_versions` ilk satırları göçle eklenir; `registry_sha256`/`config_sha256` göç sırasında hesaplanıp doğrulanır.
- Yayımlanmış bir sürüm satırı **asla** göçle değiştirilmez; düzeltme yeni sürümdür (V5).

### 9.4 Testler

- Boş veritabanından tüm zincir uygulanır (`pytest` + gerçek PostgreSQL 16 konteyneri `[B]`; `sqlite` ile test edilmez, `jsonb`/RLS/tetikleyici farklıdır).
- Eski şemadan yeniye göç testi (önceki faz dump'ı).
- **Değiştirilemezlik testi:** uygulama rolüyle `UPDATE findings` ve `DELETE findings` başarısız olmalı.
- **RLS testi:** bağlamsız oturum 0 satır görür; kiracı A bağlamı kiracı B satırı yazamaz (`WITH CHECK`).
- **Bileşik FK testi:** `audit_pages.tenant_id` ≠ `audits.tenant_id` ekleme reddedilir.
- **Sır sızıntı testi:** BYOK anahtarı sahte bir değerle eklenir; uygulama günlüğü, hata çıktısı ve `payload_ref` içeriğinde bu değerin aranması boş dönmeli.
- Büyüme: `findings` ve `page_fetches` yüksek hacimde **zaman aralığı bölümlemesi** (`created_at`) gerektirebilir; MVP'de bölümleme yok, eşik ölçümle belirlenir `[?]` (DM7).

## 10. Doğrulama matrisi (kaynak ↔ bu belge)

### 10.1 kaynak proje drift şeması (kaynak kodla kontrol edildi)

| İddia | Kaynak | Sonuç |
|---|---|---|
| Drift deposu tek SQLite dosyasıdır: `~/.cache/kaynak-proje/drift/baselines.db`, `journal_mode=WAL` | `drift_baseline.py:12,36,95` | ✅ |
| `baselines` tablosu **17 kolon**: `id, url, url_hash, timestamp, title, meta_description, canonical, robots, h1, h2_json, h3_json, schema_json, og_json, cwv_json, html_hash, schema_hash, status_code` | `drift_baseline.py:97-115` | ✅ |
| `comparisons` tablosu **9 kolon**: `id, url, url_hash, baseline_id, timestamp, results_json, critical_count, warning_count, info_count` (`baseline_id` FK → `baselines.id`) | `drift_baseline.py:121-133` | ✅ |
| İki indeks: `idx_url_hash` (`baselines.url_hash`), `idx_comp_url_hash` (`comparisons.url_hash`) | `drift_baseline.py:118,135` | ✅ |
| JSON alanları `TEXT` olarak saklanır (`*_json`), karşılaştırma sonucu tek `results_json` blob'udur | `drift_baseline.py:97-115`, `drift_compare.py:544-554` | ✅ |
| `url_hash` = normalize URL'in SHA-256'sının **ilk 16 hex karakteri (64 bit)** | `drift_baseline.py:81-84` | ✅ |
| `drift_baseline.normalize_url`: şema/host küçük harf, varsayılan port atılır, sorgu parametreleri **sıralanır**, yalnız **5 UTM** parametresi (`utm_source/medium/campaign/term/content`) atılır, sondaki `/` atılır, fragment ve `;params` atılır | `drift_baseline.py:39,46-78` | ✅ |
| Ayrı bir normalleştirici daha var: `page_checks.canonicalize_url`/`url_match_key` (IDNA host, yüzde-kaçış tek yazım, `utm_*` + `fbclid/gclid/mc_*/_ga/ref` atılır, sorgu **sıralanmaz**, çift eğik çizgi birleştirilir, `url_match_key` sondaki `/`'ı yok sayar) | `page_checks.py:413-452` | ✅ iki farklı kural seti |
| Drift 17 kural: 8 CRITICAL / 6 WARNING / 3 INFO | `drift_compare.py` (belge 01 §12'de doğrulandı) | ✅ |
| Tek kullanıcılı yerel dosya, kiracı/site/denetim bağlantısı yok | `drift_baseline.py` (`DB_PATH` kullanıcı önbelleği) | ✅ |

**Bizim şemanın kaynaktan farkları:**

| Konu | kaynak proje | Bizde | Neden |
|---|---|---|---|
| Depolama | Yerel SQLite, tek kullanıcı | PostgreSQL, kiracılı, RLS | Çok kullanıcılı SaaS |
| Kimlik | `INTEGER AUTOINCREMENT` | UUIDv7 | Dağıtık üretim, sıra tahmin edilemez |
| URL anahtarı | 64 bit kısaltılmış hash | `url_match_key` metin + (gerekirse tam SHA-256) | 64 bit çakışma riski; okunabilirlik |
| JSON | `TEXT` | `jsonb` | Sorgulanabilirlik |
| Karşılaştırma | Tek `results_json` blob | Tetiklenen kural başına `drift_events` satırı | Uyarı akışı ve filtreleme |
| Bağlam | Denetim/site bağı yok | `audit_id`, `site_id`, `page_id` FK | Çekirdek sayfa ve trend (belge 00 §3.3) |
| URL normalizasyonu | Drift'te ayrı, daha zayıf (IDN/yüzde-kaçış yok) | Tek kural: `page_checks.url_match_key` mantığı | Aynı sayfa, iki tutarsız anahtar olmasın |

### 10.2 Sözleşme ve önceki belgelerle tutarlılık

| Kontrol | Sonuç |
|---|---|
| Bulgu alanları = belge 01 §6 JSON'u (`recommendation/effort/impact` ayrı tabloda, V6) | ✅ bilinçli bölme |
| Skor alanları = belge 01 §8 (kategori skoru, ağırlık', kapsam, kapı, güven, `score_version`) | ✅ |
| `coverage` JSONB = belge 05 §9.4 şeması | ✅ |
| `page_fetches` alanları = belge 05 §6.5 | ✅ |
| `not_checked.reason_code` listesi = belge 05 §12 (14 kod) | ✅ |
| `audit_stages.stage` listesi = ortak sözleşme (12 değer) | ✅ |
| Çekirdek/keşif = belge 00 §3.3; trend yalnız çekirdek | ✅ |
| Önbellek anahtarı = belge 01 §4.1 | ✅ |

### 10.3 Doğrulanmadı

- PostgreSQL 16'da yerel UUIDv7 olmadığı bilgisi (sürüm notlarından kontrol edilmeli); uygulama tarafı UUIDv7 kütüphanesi seçilmedi.
- Arq'nın güncel bakım durumu ve sürümü; SQLAlchemy 2 + async sürücü (`asyncpg`) birleşimi.
- RLS + PgBouncer **işlem** havuzlaması: `set_config(..., true)` ile uyum teoride tamam, prototiple test edilecek.
- `zstd` sıkıştırma kütüphane desteği ve nesne depolama IAM koşullarıyla önek zorlaması (sağlayıcıya bağlı).
- Tetikleyicilerin yazma yüküne etkisi ve bölümleme eşiği (ölçülmedi).
- KMS/zarf şifreleme ürün seçimi (bulut sağlayıcıya bağlı).
- Hukuki konular (§6.5).

## 11. Açık kararlar

| # | Karar | Öneri | Not |
|---|---|---|---|
| DM1 | Başlık Health Score hangi tabanı kullanır: `all` mı `core` mu? | Tek seferlik denetimde **`all`**; trend yalnız **`core`** (iki satır saklanır) | Belge 00 §3.3 yalnız trendi çekirdeğe bağlar; başlık skoru belirtilmemişti |
| DM2 | `llm_cache` kiracılar arası paylaşılsın mı? | Hayır, kiracı başına | Paylaşım maliyeti düşürür; ama kiracı verisi ve BYOK ilişkisi karışır |
| DM3 | Ham HTML saklama süresi ve sıkıştırma | 30 gün, `zstd` | Hukuki ve maliyet |
| DM4 | UUIDv7 üretici kütüphane | Seçilecek | |
| DM5 | `findings.evidence` içinde kişisel veri riski | 200 karakter + maskeleme | Hukuki inceleme |
| DM6 | `sites` kimliği için "kayıtlı alan adı" (Public Suffix List) kullanılsın mı | İlk sürümde yalnız `origin` | `www`/apex eşleştirmesi belge 05 §4'te |
| DM7 | `findings`/`page_fetches` bölümleme eşiği | MVP'de yok, ölçümle | |
| DM8 | Rapor JSON anlık görüntü mü, istek anında üretim mi | **Anlık görüntü** (§3.16) | Paylaşılan rapor sabit kalır |
| **DM9** | **Sapma:** `tier` kullanıcıda değil **sitede** (`sites.tier`) | Sitede | Doğrulama bir siteye aittir; aynı kullanıcı bir siteyi doğrulayıp diğerini doğrulamamış olabilir |
| **DM10** | **Sapma:** `findings.layer` yalnız `A`/`B` (sözleşme `A|B|C`) | A/B; C öneri ve danışma skoru üretir | Katman C bulgu üretmez (belge 01 §4); `finding_advice` bu ayrımı taşır |
| **DM11** | **Ek tablolar:** `page_scores`, `finding_advice` | Eklendi | P25 dağılımı, çekirdek sayfa trendi ve değiştirilemez bulgu için gerekli |

DM9-DM11 ortak sözleşmeyle çelişen/genişleten noktalardır; belge 05/06 bu üçüne uyum sağlamalıdır.

## 12. Sonraki belgeler

| Belge | Konu | Bu belgeden devraldığı |
|---|---|---|
| Belge 05 (sistem tasarımı) | İş kuyruğu, worker, fan-out, checkpoint, bütçe/kota uygulaması | `audit_stages`, `usage_ledger`, `audits.budget/cost`, roller ve RLS bağlamı |
| Belge 06 (G/Ç şemaları) | API ve rapor JSON şeması | Rapor sorgusu (§7.1), `reports`, `qa_*` sözleşmesi, DM9-DM11 |
| Belge 07 (özellikler) | Faz bazlı özellik listesi | §8.1 faz-tablo eşlemesi |
| Belge 08 (dosya yapısı) | Python paket ve dizin yapısı | Alembic düzeni, model/repository ayrımı |
