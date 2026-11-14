# 08. Dosya ve Modül Yapısı: Depo Ağacı, Sınırlar, Portlama Haritası

> Durum: **Taslak v0.1** · Girdi: belge 00-02, 05, 09 ve `kaynak/` kaynak kodu
> İşaretler: `[K]` kaynak projeden alındı · `[B]` bizim kararımız · `[?]` açık karar · `[doğrulandı]` kaynak kodla/dosyayla kontrol edildi
> **Belge numaraları (nihai):** 00 capability-parity · 01 evaluation-system · 02 agent-arhitecture (iş hattı, worker'lar) · 03 rubrik-and-prompts · 04 data-model · 05 system-design (genel sistem + fetch/crawl/SSRF) · 06 io-schemas (API + `audit.json`) · 07 features · 08 file-structure (bu belge) · 09 implementation-roadmap · 10 decision-log.
> Yığın: Python ≥ 3.11 (kaynakla aynı `requires-python = ">=3.11"` `[doğrulandı: pyproject.toml]`). Kütüphane ve araç seçimleri `[B]` önerisidir; Faz 0'da doğrulanır.

---

## 1. Bu belgenin görevi

Belge 09 §3 depo yapısını **ana hatlarıyla** çizdi. Bu belge onu genişletir: her dizinin sorumluluğu, paketler arası bağımlılık kuralları, kaynak projeden **hangi dosyanın nereye, hangi fazda, hangi testle** taşınacağı, veri/yapılandırma/test/dağıtım/CI düzeni.

Amaç iki hatayı önlemek:
1. **Sessiz kayıp** (belge 00): taşınan bir davranışın testsiz kalması.
2. **Mimari erozyonu**: saf çekirdeğin (`checks`, `scoring`, `parse`) zamanla ağ/DB/saat bağımlılığı kazanması; kullanıcı URL'si çeken kodun `safefetch` dışına sızması (belge 05 §5).

### 1.1 Belge 09 §3'e göre farklar
| Eklenen | Gerekçe |
|---|---|
| `domain/` | Enum ve ortak modeller tek yerde (belge 04 sözleşmesi); saf çekirdek DB modeline bağımlı olmasın |
| `facts/`, `data/` düzeni | Kural/olgu verisi sürümlü ve kaynaklı (§5) |
| `integrations/` | Sabit hedefli dış API'ler (PSI, CrUX, GSC); kullanıcı URL'si çeken `safefetch`'ten ayrı |
| `storage/`, `security/`, `config/`, `observability/` | Belge 02 §15 ve belge 04 gereksinimleri |
| `checks/page/` alt paketi | Kaynaktaki 1180 satırlık tek dosya kontrol ailelerine bölünür |
| `third_party/kaynak_proje/` + `tests/parity/` | Parity koşucusunun karşılaştıracağı sabitlenmiş kaynak anlık görüntüsü (§7) |
| `deploy/`, `docs/adr/` | Dağıtım ve karar kaydı |

## 2. Depo ağacı

```
seo-analyzer/
├── pyproject.toml                 # bağımlılıklar, ruff, mypy, pytest, import-linter
├── uv.lock | requirements.lock    # kilit dosyası (araç seçimi [?])
├── NOTICE                         # kaynak proje MIT telif + taşınan dosya listesi (§4.9)
├── LICENSE
├── README.md
├── .env.example                   # yalnız değişken adları, gerçek değer yok (§6)
├── .pre-commit-config.yaml
├── .github/
│   ├── CODEOWNERS
│   ├── dependabot.yml
│   └── workflows/                 # ci.yml, release.yml, parity-refresh.yml (§13)
├── src/seoa/
│   ├── domain/                    # enum'lar, ortak modeller, hata türleri (saf)
│   ├── parse/                     # bayt/metin → yapı: html, jsonld, robots, sitemap_xml, encoding (saf)
│   ├── checks/                    # kontrol kaydı + Katman A/B kontrolleri (saf)
│   ├── scoring/                   # ağırlık, ceza, kapı, kapsam, güven (saf)
│   ├── crawl/                     # URL normalizasyon, şablon kümeleme, örneklem (saf) + keşif orkestrasyonu
│   ├── facts/                     # data/ yükleyicileri ve doğrulayıcıları (salt-okunur)
│   ├── render/                    # spa.py, js_gap.py (saf) + browser.py, guard.py (Playwright)
│   ├── safefetch/                 # kullanıcı URL'si için TEK dış ağ giriş noktası (SSRF)
│   ├── integrations/              # sabit hedefli dış API'ler: psi, crux, (gsc: Faz 3)
│   ├── llm/                       # sağlayıcı arayüzü, modüller, prompt/rubrik, önbellek, bütçe, kanıt doğrulama
│   ├── schemagen/                 # JSON-LD üreticileri (Faz 2c)
│   ├── drift/                     # drift kuralları ve baseline mantığı (Faz 3)
│   ├── pipeline/                  # durum makinesi, aşamalar, worker giriş noktaları, kuyruk/limit adaptörleri
│   ├── report/                    # audit.json derleme + şema, HTML, i18n, (pdf: Faz 3)
│   ├── api/                       # FastAPI uygulaması, rotalar, şemalar, hata modeli, SSE
│   ├── db/                        # SQLAlchemy modelleri, depolar, oturum, RLS yardımcıları
│   ├── storage/                   # nesne depolama istemcisi ve anahtar düzeni
│   ├── security/                  # zarf şifreleme (BYOK), sır yönetimi, dış istek kaydı, kötüye kullanım
│   ├── config/                    # pydantic-settings sınıfları (servis başına)
│   ├── observability/             # günlük, metrik, izleme
│   └── cli/                       # geliştirici/operasyon komutları (kural yükle, yeniden skorla, golden üret)
├── data/
│   ├── rules/                     # eşikler, ağırlıklar, politika listeleri (sürümlü JSON)
│   ├── facts/                     # olgu defterleri (google-updates.json portu)
│   ├── lang/{tr,en}/              # stopword, filler, CTA listeleri
│   └── seed/                      # geliştirme tohum verisi
├── migrations/                    # Alembic: alembic.ini, env.py, versions/
├── tests/                         # unit · golden · hostile · parity · integration · e2e · architecture (§7)
├── third_party/kaynak_proje/        # sabitlenmiş kaynak anlık görüntüsü (yalnız parity testleri okur)
├── deploy/
│   ├── docker/                    # çok aşamalı Dockerfile, worker türü başına hedef
│   ├── compose/                   # docker-compose.dev.yml
│   ├── egress/                    # egress proxy yapılandırması ve ACL'ler
│   └── k8s/                       # NetworkPolicy ve dağıtım manifestleri (Faz 2a)
├── scripts/                       # geliştirici betikleri (parity çıkarımı, snapshot, golden)
└── docs/
    ├── architecture/              # bu belgeler
    ├── kaynak analizi notları         # kaynak analizi
    └── adr/                       # tekil karar kayıtları (§12)
```

### 2.1 `src/seoa/` paketleri: sorumluluk

| Paket | Tek satırlık sorumluluk | Saf mı | Ağ | Faz |
|---|---|---|---|---|
| `domain` | `AuditMode`, `AuditStatus`, `Stage`, `Layer`, `Severity`, `Category`, `Finding`, `NotChecked`, `CheckDef`, hata sınıfları | ✅ | yok | 0 |
| `parse` | `html.py` (SEO öğeleri), `jsonld.py` (@graph düzleştirme, sınırlar), `robots.py` (RFC 9309 grupları), `sitemap_xml.py`, `encoding.py` (BOM → header → meta → utf-8) | ✅ | yok | 1 |
| `checks` | `registry.py`, `base.py`, `page/*` (Katman A), `transport.py`, `robots_site.py`, `sitemap.py`, `schema.py`, `performance.py`, `ai_readiness.py`, `lang/` (dil kapıları), `heuristics/` (Katman B) | ✅ | yok | 1+ |
| `scoring` | `weights.py`, `score.py`, `gate.py`, `coverage.py`, `versions.py` (belge 01 §8) | ✅ | yok | 1 |
| `crawl` | `normalize.py` (`canonicalize_url`, `url_match_key`), `templates.py` (şablon kümeleme), `sampling.py` (tohumlu, tabakalı) saf; `discovery.py` `safefetch` kullanır | kısmen | `safefetch` üzerinden | 1-2a |
| `facts` | `data/` JSON'larını yükler, Pydantic ile doğrular, hash ve `last_verified` döndürür | salt-okunur dosya | yok | 1 |
| `render` | `spa.py` (`_is_spa`), `js_gap.py` saf; `browser.py` (Playwright), `guard.py` (route handler) | kısmen | proxy üzerinden | 2a |
| `safefetch` | `policy.py`, `resolver.py`, `fetcher.py`, `limits.py`, `tls_probe.py`, `robots_fetch.py` | ❌ | **tek giriş** | 0 |
| `integrations` | PSI/CrUX (Faz 2a), GSC (Faz 3); sabit ana bilgisayar izin listesi | ❌ | sabit hedef | 2a+ |
| `llm` | `client.py`, `providers/`, `modules/`, `prompts/`, `rubrics/`, `cache.py`, `budget.py`, `grounding.py` | modüller kısmen | yalnız sağlayıcı | 2b |
| `schemagen` | `reservation`, `order_action`, `discussion`, `profile` üreticileri + doğrulama | ✅ | yok | 2c |
| `drift` | `rules.py` (17 kural), `baseline.py`, `compare.py` | ✅ (depo hariç) | yok | 3 |
| `pipeline` | `orchestrator.py`, `stages/` (aşama başına modül), `workers/`, `queue.py`, `limits.py` (Redis), `events.py` | ❌ | yok | 1+ |
| `report` | `build.py`, `schema.py` (Pydantic `AuditJSON`), `render_html.py`, `templates/`, `i18n/` | ✅ (üretim) | yok | 1 |
| `api` | `app.py`, `deps.py`, `auth.py`, `routes/`, `schemas/`, `errors.py` (problem+json), `sse.py` | ❌ | yok | 1 |
| `db` | `models/`, `repositories/`, `session.py`, `rls.py` | ❌ | DB | 0 |
| `storage` | `client.py`, `keys.py` (§9) | ❌ | nesne depolama | 1 |
| `security` | `crypto.py`, `secrets.py`, `audit_log.py`, `abuse.py` | ❌ | yok | 1-2b |
| `config` | `ApiSettings`, `FetchSettings`, `RenderSettings`, `AnalyzeSettings`, `LlmSettings`, `ControlSettings`, `ReportSettings` | – | yok | 0 |
| `observability` | `logging.py`, `metrics.py`, `tracing.py` | ❌ | yok | 0 |
| `cli` | `seed_rules`, `rescore`, `regen_golden`, `run_checks_on_file` | ❌ | yok | 0 |

`checks/page/` iç düzeni (kaynaktaki 47 kontrolün aileleri `[doğrulandı: page_checks.CHECKS]`):

| Dosya | Kontroller (kaynak id'leri) |
|---|---|
| `title.py` / `meta.py` | `missing-title`, `title-too-long`, `title-too-short`, `missing-meta-description`, `meta-description-too-long`, `duplicate-meta-tags` |
| `headings.py` | `missing-h1`, `multiple-h1`, `heading-level-skip` |
| `indexing.py` | `missing-canonical`, `canonical-points-elsewhere`, `noindex`, `noindex-header`, `nofollow`, `meta-refresh-redirect`, `hreflang-missing-self` |
| `document.py` | `missing-doctype`, `missing-charset`, `charset-mismatch`, `missing-lang`, `missing-viewport`, `uses-frames`, `deprecated-html-tags`, `placeholder-text`, `html-over-2mb`, `deep-dom`, `wide-dom-node` |
| `images.py` | `images-missing-alt`, `images-missing-dimensions`, `first-image-lazy-loaded` |
| `links.py` | `links-without-text`, `generic-anchor-text`, `links-to-http`, `mixed-content` |
| `urls.py` | `url-too-long`, `url-has-parameters`, `url-uppercase`, `url-underscores`, `url-non-ascii`, `url-double-slash` |
| `social.py` | `og-url-differs-from-canonical`, `missing-open-graph`, `missing-og-image` |
| `structured.py` | `invalid-jsonld` |
| `relevance.py` | `title-not-reflected-in-content`, `description-not-reflected-in-content` (dil kapılı, belge 01 §4.0), `thin-content` |

## 3. Modül sınırları ve bağımlılık kuralları

### 3.1 Katmanlar

```
 L4  Giriş noktaları      api · pipeline.workers · cli
            │ (yalnız aşağıyı import eder)
 L3  Servisler            pipeline (orkestratör, aşamalar) · report · llm.modules · drift (depo katmanı)
            │
 L2  Adaptörler (I/O)     safefetch · integrations · db · storage · llm.providers · queue/limits · security
            │
 L1  Saf çekirdek         parse · checks · scoring · crawl(saf kısım) · render(spa, js_gap) · schemagen · drift.rules · facts
            │
 L0  Alan                 domain
```

Kural: **bir katman yalnız kendi altındakini import eder.** Yukarı veya yanlamasına (aynı katmanda ilgisiz paket) bağımlılık yasak; istisnalar §3.2'de listelenir.

### 3.2 Kurallar

| # | Kural | Gerekçe |
|---|---|---|
| **B1** | **Saf çekirdek** (`domain`, `parse`, `checks`, `scoring`, `schemagen`, `drift.rules`, `crawl` saf modülleri, `render.spa`, `render.js_gap`) **şunları import edemez:** `aiohttp`, `requests`, `httpx`, `socket`, `ssl`, `sqlalchemy`, `redis`, `playwright`, `boto3`, `subprocess`. Saat ve rastgelelik **parametre** olarak gelir (`now`, `rng`/tohum); `datetime.now`, `time.time`, `random`, `os.environ` kullanılamaz | Belge 01 P1/P5: aynı girdi → aynı çıktı; golden ve yeniden skorlama mümkün (belge 02 §11) |
| **B2** | **Kullanıcı kontrollü URL'ye giden tüm ağ trafiği `seoa.safefetch` üzerinden geçer.** `aiohttp`/`socket`/`ssl` yalnız `safefetch` içinde import edilir. `render.browser` Playwright'ı kullanır ama `safefetch.policy`'yi import edip route handler'da her alt isteği doğrular (`render.guard`) | Belge 05 §5; kaynaktaki tek-kapı ilkesi (`url_safety` herkesin geçtiği alt katman `[doğrulandı: fetch_page/parse_html/render_page/sitemap_discovery/transport_check hepsi url_safety'den import eder]`) |
| **B3** | **Sabit hedefli** dış servisler (DB, Redis, nesne depolama, LLM sağlayıcısı, PSI/CrUX/GSC) kendi adaptörlerinden gider: `db`, `pipeline.limits`, `storage`, `llm.providers`, `integrations`. Bu adaptörler **kullanıcı girdisinden ana bilgisayar adı türetemez**; hedef ana bilgisayarlar yapılandırmada sabit | SSRF yüzeyini tek kapıda tutar. PSI çağrısında kullanıcı URL'si Google'a **parametre** olarak gider, bizim çıkış hedefimiz değildir |
| **B4** | `db` modelleri L1'e sızmaz; saf çekirdek `domain` modelleriyle konuşur, `db.repositories` eşler | Çekirdeğin DB'siz test edilebilmesi |
| **B5** | `pipeline` ve `api` birbirini import etmez; ikisi de `report`, `db`, `llm.modules` gibi servis/adaptörleri kullanır | İş mantığı iki girişte de aynı |
| **B6** | Döngüsel import yok | Okunabilirlik, import-linter zaten zorlar |
| **B7** | `checks.*` modülleri **birbirini import etmez**; ortak kod `checks/base.py` veya `parse/`'a çıkar. Her kontrol `CheckDef` kaydıyla `registry`'ye kendini ekler | Kaynak tek dosyadaki ortak durumdan kaçınır, bağımsız test |
| **B8** | `llm.modules`, `llm.providers`'ı yalnız `client.py` arayüzü üzerinden kullanır; ham HTML yerine `parse/` çıktısı alır | Belge 02 §9.3 (ham HTML modele verilmez) |
| **B9** | `third_party/` yalnız `tests/parity` ve `scripts/` tarafından okunur; `src/seoa` hiçbir zaman import etmez | Lisans ve bağımlılık hijyeni |

### 3.3 Zorlama: import-linter + ruff `[B, doğrulanmadı]`

Öneri: **import-linter** katman ve yasak-import sözleşmeleri, tamamlayıcı olarak **ruff** `flake8-tidy-imports` (`TID251` banned-api) ve bir **AST testi**.

```toml
# pyproject.toml (taslak; sözdizimi Faz 0'da doğrulanır)
[tool.importlinter]
root_package = "seoa"
include_external_packages = true

[[tool.importlinter.contracts]]
name = "Katmanlı mimari"
type = "layers"
layers = [
  "seoa.cli | seoa.api | seoa.pipeline.workers",
  "seoa.pipeline | seoa.report | seoa.llm.modules | seoa.drift.service",
  "seoa.safefetch | seoa.integrations | seoa.db | seoa.storage | seoa.llm.providers | seoa.security",
  "seoa.parse | seoa.checks | seoa.scoring | seoa.crawl | seoa.render | seoa.schemagen | seoa.facts",
  "seoa.domain",
]

[[tool.importlinter.contracts]]
name = "Saf çekirdek ağ/DB/tarayıcı import edemez"
type = "forbidden"
source_modules = ["seoa.domain", "seoa.parse", "seoa.checks", "seoa.scoring", "seoa.schemagen"]
forbidden_modules = ["aiohttp", "requests", "httpx", "socket", "ssl", "sqlalchemy", "redis", "playwright", "boto3"]

[[tool.importlinter.contracts]]
name = "Dış HTTP istemcileri yalnız safefetch/integrations/llm.providers/storage'da"
type = "forbidden"
source_modules = ["seoa.checks", "seoa.crawl", "seoa.render", "seoa.pipeline", "seoa.report", "seoa.api"]
forbidden_modules = ["aiohttp", "requests", "httpx"]
```

| Doğrulanması gereken | Neden |
|---|---|
| import-linter'ın **standart kütüphane** modüllerini (`socket`, `ssl`) `forbidden` sözleşmesinde yakalayıp yakalamadığı | Yakalamıyorsa B1'in `socket/ssl/subprocess` kısmı ruff `TID251` ve AST testiyle sağlanır |
| `TID251`'in dizin bazlı uygulanabilirliği (global yasak + `per-file-ignores` ile `safefetch/`'e istisna) | Saf çekirdeğe özel yasak ancak böyle kurulabilir |
| `datetime.now`, `time.time`, `random.*`, `os.environ` için ruff/AST yasağı | Saat/rastgelelik kuralı B1 |

Yedek: `tests/architecture/test_purity.py` saf paketlerin AST'sini tarar (yasak import, yasak çağrı) ve CI'da çalışır; import-linter sözleşmeleriyle **ikisi birden** koşulur (biri yanlışlıkla gevşerse diğeri tutar).

## 4. Portlama haritası: kaynak proje → hedef modül

Kaynak: `kaynak/scripts/*.py` (**63 dosya, `wc -l` toplamı 32 340 satır** `[doğrulandı]`), `hooks/validate-schema.py` (371 satır), `data/`, `schema/`, `skills/seo/references/`. Kaynak sabitlenir: commit `cca7e4a267991aca880efade1fd12e8498caf2ce` (2026-11-11, `git log -1`) `[doğrulandı]`.

Durum: **Taşı** (mantık aynen) · **Böl-taşı** (parçalanarak) · **Yeniden yaz** (davranış korunur, uygulama değişir) · **Ertele** (faz hedefi var) · **Taşıma** (bilinçli, belge 00 §3).
Faz numaraları belge 09'a göredir. "Test" sütunu `tests/` altında **gerçekten var olan** dosyalardır; parantez içinde `def test_` sayısı (parametrelendirmeler hariç) `[doğrulandı]`.

### 4.1 Çekirdek: Faz 1 (kaynak ≈ 5 454 satır, hook dahil)

| Kaynak (satır) | Hedef | Durum | Testler | Not |
|---|---|---|---|---|
| `page_checks.py` (1180) | `checks/page/*`, `checks/registry.py`, `crawl/normalize.py`, `checks/lang/` | **Böl-taşı** | `test_page_checks.py` (43) | `CHECKS` sözlüğü 47 kontrol → `CheckDef` kayıtları; eşik sabitleri → `data/rules/thresholds.json` (§5); `STOPWORDS` yalnız İngilizce `[doğrulandı: satır 236]` → `data/lang/en/`; `_from_file/_from_url/main` (CLI) taşınmaz, yerini pipeline alır. Testin tüm HTML'i **satır içi**, ağ yok `[doğrulandı]` |
| `parse_html.py` (917) | `parse/html.py`, `parse/jsonld.py` | **Taşı** (bağımlılıkları sök) | `test_parse_html_extraction.py` (42), `_inline_spacing`, `_malformed_urls`, `_rel_case`, `test_document_base_url.py` (6), `test_lazy_detection.py` (11), `test_image_format_probe.py` | Kaynak `requests` ve `url_safety` import eder (satır 84-85 `[doğrulandı]`); saf çekirdek için bu bağlar kesilir, ağ kısmı `safefetch`'e gider |
| `url_safety.py` (1442) | `safefetch/policy.py`, `safefetch/resolver.py`, `safefetch/limits.py`, `parse/encoding.py`, `render/guard.py` | **Böl-taşı + Yeniden yaz** | `test_url_safety.py` (72), `test_url_safety_ipv6.py` (45), `test_url_safety_port_pin.py` (14), `test_redirect_body_cap.py` (6), `test_fetch_page_size_cap.py` (4) | Politika (`is_safe_ip`, `_BLOCKED_HOSTNAMES`, `_reject_authority_confusion`, `normalize_hostname`, DNS64, `validate_url_strict`) **Taşı**; `_pin_dns` global `getaddrinfo` yaması **Taşıma** → `SafeResolver` (belge 05 §5.2); `LOCAL_TARGETS` bloğu **Taşıma** (belge 00 L1); `decode_body` → `parse/encoding.py`; Playwright route handler → `render/guard.py`. **Test uyarısı: §7.4** |
| `fetch_page.py` (468) | `safefetch/fetcher.py` (aiohttp, async) | **Yeniden yaz** | `test_fetch_page_decoding.py` (13), `test_fetch_page_size_cap.py` (4), `test_redirect_body_cap.py` (6), `test_fetch_page_timing.py` | `--googlebot` ve CLI taşınmaz (belge 00 L2); sonuç alanları (`status_code`, `content`, `headers`, `redirect_chain`, `ttfb_ms`, `content_bytes`) belge 05 §6.5 sözleşmesine |
| `transport_check.py` (1076) | `safefetch/tls_probe.py` (toplama) + `checks/transport.py` (değerlendirme) | **Böl-taşı** `[B]` | `test_transport_check.py` (52) | Kaynak tek dosyada hem el sıkışmayı hem kararı yapar; saf değerlendirme ayrılırsa golden test edilebilir. Ayrılabilirliği kod okunurken doğrulanacak `[?]` |
| `hooks/validate-schema.py` (371) | `checks/schema.py`, `data/rules/schema-policy.json` | **Böl-taşı** | `test_schema_hook_detection.py`, `test_schema_hook_policy.py`, `test_schema_hook_redos.py`, `test_schema_graph_semantics.py` (7) | `BRACKET_PLACEHOLDERS` (9 öğe) + `REPLACE…` düzenli ifadesi + kullanımdan kalkmış/emekli tipler. Script etiketi ayrıştırıcısı **ReDoS** önlemli yazılmış `[doğrulandı: yorumlar]`; regex birebir taşınır ve ReDoS testi korunur. Hook'un Claude Code'a özgü kısmı (stdin/exit code, JSX/Vue şablon ifadeleri) taşınmaz |

### 4.2 Faz 2a: site modu, render, performans, AI hazırlığı (≈ 4 320 satır)

| Kaynak (satır) | Hedef | Durum | Testler | Not |
|---|---|---|---|---|
| `sitemap_discovery.py` (916) | `parse/sitemap_xml.py`, `crawl/discovery.py` | **Böl-taşı** | `test_sitemap_discovery.py` (20), `test_sitemap_expand.py` (41), `test_sitemap_bom.py` (5), `test_sitemap_news_limit.py` | Sınırlar aynen: 50 MiB, 50 000 URL, 16 bildirilen, 50 çocuk `[doğrulandı: satır 63-80]`. Kaynak `requests`+`lxml` kullanır; `lxml` kalır, ağ `safefetch`'e |
| `render_page.py` (1060) | `render/spa.py` (`_is_spa`), `render/js_gap.py` (`js_gap`, `js_gap_reasons`, `_gap_signals`), `render/browser.py` (async Playwright), `parse/jsonld.py` (JSON-LD sınırları) | **Böl-taşı + Yeniden yaz** | `test_render_js_gap.py` (21), `test_render_page.py` (38) | Eşikler belge 05 §7'de doğrulanmıştı (400/100 karakter; %30/25 kelime/3 link). Erişilebilirlik ağacı yakalama MVP'de **taşınmaz** |
| `pagespeed_check.py` (674) | `integrations/psi.py` + `checks/performance.py` (`rate_metric`, `CWV_THRESHOLDS`) | **Böl-taşı** | `test_pagespeed_null_category_score.py` (3), `test_pagespeed_psi_only_exit.py` | Eşikler (`2500/4000`, `200/500`, `0.1/0.25` ms/birim) `data/rules/cwv.json`'a `[doğrulandı: CWV_THRESHOLDS]` |
| `crux_history.py` (336) | `integrations/crux.py` + saf `detect_trends` | **Böl-taşı** | `test_crux_history_trends.py` (2) | Trend mantığı Faz 3'te kullanılır |
| `agentic_check.py` (1334) | `parse/robots.py` (RFC 9309 grup seçimi), `checks/ai_readiness.py` | **Böl-taşı** (yalnız robots AI botları + `js_gap` girdisi) | `test_agentic.py` (66), `test_ai_crawler_claims.py` (16), `test_llms_txt_validation.py` (27) | llms.txt/Markdown/ARD/WebMCP kısımları Faz 4+; bot sınıflandırması (eğitim/arama/kullanıcı-tetikli) `data/rules/ai-crawlers.json` |

### 4.3 Faz 2b/2c: Katman B/C destek verisi ve schema üretimi (≈ 1 861 satır)

| Kaynak (satır) | Hedef | Durum | Testler | Not |
|---|---|---|---|---|
| `metadata_template.py` (399) | `checks/heuristics/metadata_template.py` | **Yeniden yaz** (algoritma taşınır, Türkçe/İngilizce listeler bizim) | `test_metadata_template.py` (27) | Başlık-yankısı + stok CTA fikri korunur; İngilizce CTA listesi taşınmaz, `data/lang/*/cta.json` bizim üretimimiz (belge 00 §3.5) |
| `content_quality.py` (378), `content_verify.py` (194) | `checks/heuristics/*` | **Ertele** (Türkçe listelerle birlikte) | `test_content_quality.py` (41; `content_humanize`, `content_verify`, `domain_history`, `seo_updates` testlerini de içerir) | Kalıp listeleri Wikipedia "AI Cleanup" (CC BY-SA 4.0) kaynaklı `[belge 00 §6, 05 raporu]` → **taşınmaz**. Hangi kısımların algoritma, hangilerinin liste olduğu satır satır okunmadı **(doğrulanmadı)** |
| `seo_updates.py` (210) | `facts/google_updates.py` | **Taşı** | `test_content_quality.py` içindeki `test_seo_updates_*` | `data/facts/google-updates.json` ile birlikte (§5) |
| `schema_generate.py` (349) | `schemagen/*` (4 üretici: `reservation`, `order_action`, `discussion`, `profile`) | **Taşı** | `test_schema_v2.py` (25) | Üretilen çıktı kendi validator'ımızdan geçer, deprecated tip önerilmez (belge 09 §8) |
| `schema_ecommerce_validate.py` (331) | `checks/schema_ecommerce.py` | **Ertele** (e-ticaret dikeyi) | `test_schema_v2.py` | |

### 4.4 Faz 3: izleme, doğrulanmış sahip, Google verisi (≈ 7 345 satır)

| Kaynak (satır) | Hedef | Durum | Testler | Not |
|---|---|---|---|---|
| `drift_compare.py` (616) | `drift/rules.py` (17 kural: 8 CRITICAL / 6 WARNING / 3 INFO `[doğrulandı]`) | **Taşı** | `test_drift_robots_directives.py` (9) | Kaynak `drift_baseline`'dan ve `google_auth.validate_url`'dan import eder (satır 29-37) → saf kurallara ayrılır, URL doğrulama `safefetch.policy` |
| `drift_baseline.py` (429) | `drift/baseline.py` + `db` (`drift_baselines`) | **Yeniden yaz** | `test_drift_url_normalization.py` (3), `test_drift_portability.py` (1) | Kaynak şeması SQLite: `baselines(id, url, url_hash, timestamp, title, meta_description, canonical, robots, h1, h2_json, h3_json, schema_json, og_json, cwv_json, html_hash, schema_hash, status_code)` + `comparisons(id, url, url_hash, baseline_id, timestamp, results_json, critical_count, warning_count, info_count)`, dosya `~/.cache/kaynak-proje/drift/baselines.db`, WAL `[doğrulandı: satır 95-135]`. Bizde PostgreSQL + `tenant_id` (belge 04 `drift_baselines`, `drift_events`). Kaynak diğer script'leri `subprocess` ile çağırır (satır 21); bizde doğrudan fonksiyon |
| `drift_history.py` (127), `drift_report.py` (375) | `drift/service.py`, `report/templates/drift.html` | **Yeniden yaz** | **Test bulunamadı** (`tests/` içinde ada göre eşleşme yok) | Kaynakta testsiz; bizde yeni test yazılır |
| `google_properties.py` (120) | `integrations/gsc/properties.py` | **Taşı** | `test_google_property_resolution.py` (12) | Fail-closed domain↔site eşlemesi; çok kiracıda tenant izolasyonuna dönüşür |
| `google_auth.py` (1171) | `integrations/google/oauth.py` (web akışı) | **Yeniden yaz** | `test_google_oauth_flow.py`, `test_google_gcloud_adc.py`, `test_google_api_key_safety.py` | Kaynak loopback `localhost:8085` CLI akışı; testler 1:1 taşınmaz |
| `gsc_inspect.py` (367), `gsc_query.py` (571), `ga4_report.py` (527), `indexing_notify.py` (325) | `integrations/gsc/*` | **Ertele** (URL Inspection öncelikli, belge 00 L2) | `test_gsc_query.py`, `test_gsc_pagination.py`, `test_gsc_totals_aggregate.py`, `test_google_property_cli.py`, `test_ga4_top_pages_errors.py`, `test_indexing_notify*.py` | |
| `google_report.py` (2717) | `report/` (HTML; PDF: Playwright `page.pdf()`) | **Yeniden yaz** | `test_google_report_full_audit.py` | WeasyPrint+matplotlib+numpy+pillow ağır bağımlılık; belge 06 kararına bağlı |

### 4.5 Faz 4+ ve taşınmayanlar

| Kaynak (satır) | Karar | Hedef/Not |
|---|---|---|
| `backlinks_auth` (609), `moz_api` (449), `commoncrawl_graph` (524), `verify_backlinks` (517), `keywordseverywhere_api` (276), `bing_webmaster` (611), `indexnow_submit` (266) | **Ertele (Faz 4+)** | Testler: `test_backlinks_auth_hardening`, `test_moz_api`, `test_commoncrawl_graph`, `test_verify_backlinks`, `test_keywordseverywhere_api`, `test_bing_webmaster`, `test_indexnow_submit` |
| `validate_backlink_report` (437) | **Fikir taşınır** | "veri yetersizse skor verme" kapısı → genel `scoring/coverage.py` (belge 01 §8.4); testler `test_backlink_score_gate.py` (10), `test_validate_backlink_report.py` (10) esin kaynağı |
| `dataforseo_costs` (600), `dataforseo_merchant` (513), `dataforseo_normalize` (475), `matomo_auth` (657), `matomo_report` (711), `unlighthouse_run` (307), `youtube_search` (355), `keyword_planner` (296), `nlp_analyze` (399) | **Ertele (Faz 4+)** | Ücretli/harici; `youtube_search` ve `keyword_planner` için kaynakta test bulunamadı |
| `capture_screenshot` (632), `analyze_visual` (228) | **Ertele (Faz 4+)** | Görsel modül; `analyze_visual` kaynakta testsiz |
| `lighthouse_agentic` (422), `agent_ux_check` (300), `agentic_fix` (392), `ucp_check` (286), `preload_check` (255), `lcp_subparts` (209) | **Ertele (Faz 4+)** | agentic/ileri performans; testler `test_agentic.py`, `test_preload_check.py` (3), `test_technical_depth.py` (20) |
| `parasite_risk` (256), `domain_history` (317), `content_humanize` (323), `gbp_deprecation_lint` (136), `iptc_ai_label` (224) | **Ertele / Taşıma** | `content_humanize` yeniden yazım üretir, tespit değil: Taşıma. Diğerleri dikey/niş |
| `runtime.py` (490), `kaynak proje` başlatıcı, `release_sign` (187), `verify_release` (148), `consistency_check` (341), `portability_check` (229), `sync_flow` (354), `hooks/run-python-hook.js` (86) | **Taşıma** | Plugin altyapısı ve SKILL.md lint'i; yerlerini konteyner, CI ve `tests/architecture` alır. Testler (`test_runtime*`, `test_python_range`, `test_consistency_check`, `test_portability`, `test_manifest_consistency`, `test_hosted_plugin_layout`, `test_manual_install_layout`, `test_windows_uninstaller`, `test_powershell_ascii`, `test_no_em_dash`, `test_audit_instructions`) taşınmaz |
| `schema/templates.json` (9 737 bayt) | **Ertele** | Faz 2c'de `schemagen` kullanımı incelenirken karar; şu an hangi koddan okunduğu **doğrulanmadı** |

### 4.6 Özet (kaynak satır, `wc -l`)

| Grup | Dosya | Satır |
|---|---|---|
| Faz 1 (scripts) | 5 | 5 083 (+ hook 371 = 5 454) |
| Faz 2a | 5 | 4 320 (agentic_check kısmen) |
| Faz 2b | 4 | 1 181 (Türkçe listelerle) |
| Faz 2c | 2 | 680 |
| Faz 3 | 11 | 7 345 (`google_report` yeniden yazılır) |
| Taşıma (plugin altyapısı) | 6 | 1 749 |
| Faz 4+ / diğer | 30 | 11 982 |
| **Toplam** | **63** | **32 340** |

Yani MVP çekirdeği (Faz 1) kaynağın yaklaşık **%16'sıdır**; Faz 2a ile **%29**. Geri kalanın büyük bölümü ertelenen modüllerdir (belge 00 §2.3).

### 4.7 Taşıma kuralları

1. **Mantığı taşı, yapıyı değil.** Kaynakta `sys.path` ile kardeş script import etme (`from url_safety import …` ve `sys.path.insert`) `[doğrulandı]` yaygındır; bizde düzgün paketler.
2. **CLI/argparse ve `print(json)` taşınmaz**; giriş noktası fonksiyon, çıktı Pydantic modeli.
3. **Davranış korunur:** her taşınan kontrol için kaynak testinin eşdeğeri **önce yeşil** (belge 00 §4). Bilinçli fark `tests/parity/expected_diffs.yaml` içinde gerekçeyle yazılır.
4. **Bağımlılıklar sökülür:** saf modül `requests`/`url_safety` import etmez (B1).
5. **İngilizce'ye özgü veri** `data/lang/en/`'e çıkar; çekirdek dil-bağımsız kalır.

### 4.8 `NOTICE` ve başlık kuralı `[K]`
Taşınan her dosyanın başında: `Kaynak: kaynak/scripts/<dosya>.py @ cca7e4a (MIT, bkz. NOTICE)`. `NOTICE` taşınan tüm dosyaları listeler. Ek atıf yükümlülükleri (belge 00 §6): `content_quality`/`content_humanize` kalıp listeleri CC BY-SA 4.0 (taşınmaz), `page_checks.py` web-obs'tan türemiştir (MIT), FLOW promptları CC BY 4.0 (taşınmaz).

## 5. Kural ve olgu veri dosyaları

### 5.1 Kaynakta durum `[doğrulandı]`
- `data/` altında **tek dosya**: `google-updates.json` (66 güncelleme, 6 `unverified`, `last_verified: 2026-11-10`). Zarf alanları: `$schema`, `source_of_truth`, `secondary_sources[]`, `last_verified`, `policy`, `_schema_doc`, `updates[]`, `unverified[]`. Politika: "her kayıt Google'a ait bir URL göstermeli; yalnız üçüncü taraflı iddialar `unverified[]`'a" `[K]`.
- Test kapısı: `test_content_quality.py` içinde `test_seo_updates_data_file_is_valid_json`, `test_seo_updates_every_entry_has_google_owned_source` ve `last_verified` okuyan bir test (satır 466) `[doğrulandı]`; tazelik eşiği **doğrulanmadı**.
- **Eşikler kodda sabit**: `page_checks.THRESHOLDS` (13 anahtar: `title_min_chars=30`, `title_max_chars=60`, `meta_description_min/max=120/160`, `url_max_chars=100`, `html_max_bytes=2_000_000`, `thin_content_min_words=200`, `dom_max_depth=32`, `dom_max_children=60`, …) `[doğrulandı: satır 124-138]`.
- **Politika bilgisi markdown'da**: `skills/seo/references/schema-types.md` (HowTo Eylül 2023, SpecialAnnouncement 31 Tem 2025 kullanımdan kalktı; FAQPage rich result 7 Mayıs 2026'da sona erdi; QAPage desteklenir), `cwv-thresholds.md`, `quality-gates.md` (sayfa tipine göre kelime eşikleri) `[doğrulandı]`.

Sonuç: kaynakta **makine-okunur kural verisi yalnız `google-updates.json`'dır**; geri kalanı kod sabiti veya prompt metnidir. Bizde kural verisi **veri dosyasına** çıkarılır (kod mantığı kodda, sayısal/politika içeriği veride), böylece sürümlenir, kaynaklanır ve skor sürümüne bağlanır (belge 01 P5).

### 5.2 Dizin düzeni `[B]`

```
data/
├── rules/
│   ├── thresholds.json        # title/description/url/html/thin/dom eşikleri (page_checks.THRESHOLDS portu)
│   ├── quality-gates.json     # sayfa tipine göre min kelime + özgün içerik % (quality-gates.md)
│   ├── schema-policy.json     # kullanımdan kalkmış/emekli tipler (tarih+kaynak), placeholder belirteçleri
│   ├── cwv.json               # LCP/INP/CLS good/poor (+ FCP, TTFB), kaynak, last_verified
│   ├── ai-crawlers.json       # bot token'ları: eğitim / arama / kullanıcı-tetikli; kaynak
│   └── weights.json           # kategori ağırlıkları, severity tabanları, tavanlar, kapı eşikleri (score_version ile bağlı)
├── facts/
│   └── google-updates.json    # kaynak dosyanın portu (MIT) + bizim doğrulayıcı
├── lang/
│   ├── en/{stopwords.txt,filler.json,cta.json}
│   └── tr/{stopwords.txt,filler.json,cta.json}   # Faz 2b (belge 00 §3.5), kaynak ve lisans başlıklı
└── seed/                      # dev tohum verisi (tenant, kullanıcı)
```

Ortak zarf (kaynaktaki `google-updates.json` zarfından türetildi `[K]`):

```json
{
  "schema_version": 1,
  "rule_set_version": "2026.11.0",
  "last_verified": "2026-11-13",
  "policy": "Her kayıt birincil kaynak göstermeli; kaynaksız iddia unverified[]'a.",
  "sources": ["https://developers.google.com/search/docs/..."],
  "entries": [{"id": "howto", "status": "removed", "date": "2023-09-01", "source": "https://..."}],
  "unverified": []
}
```

### 5.3 Sürümleme ve yükleme `[B]`
- **`rule_set_version`** (CalVer) her dosyada; değişiklik **kod incelemesi + `last_verified` güncellemesi** gerektirir.
- `facts/` yükleyicisi açılışta Pydantic ile doğrular, **dosya hash'i** hesaplar; `audits.rule_version` ve `score_version` bu hash'lere bağlanır (belge 04 `rule_versions`, `score_versions`). Sürüm değişmeden veri dosyası değişemez (CI testi: hash ↔ sürüm eşleşmesi).
- **Doğrulama testleri** (kaynaktaki desen `[K]`): her kayıt izinli bir ana bilgisayara https kaynak gösterir; `last_verified` bayat değil (eşik bizim: 90 gün `[?]`); `weights.json` kategori ağırlıkları toplamı 100; her severity için taban ve tavan tanımlı.
- Kural **mantığı** (hangi kontrol hangi kategoriye, severity override) `CheckDef` kaydında kalır; yalnız **sayısal eşik ve politika listeleri** veridedir.
- Mesaj metinleri `src/seoa/report/i18n/{tr,en}/checks.json` içinde `message_key` ile (belge 06): veri değil kod paketinin parçası, çünkü sürüm ve dağıtımla birlikte gider `[?]` (FS6).

## 6. Yapılandırma ve sırlar

### 6.1 İlkeler `[B]`
- **`pydantic-settings`** `[B, sürüm doğrulanmadı]` ile **servis başına ayrı ayar sınıfı** (`ApiSettings`, `FetchSettings`, `RenderSettings`, …). Bir worker yalnız ihtiyacı olan değişkenleri alır: **en az yetki**, sırrın yanlış sürece sızması engellenir (belge 02 §3.1: Fetch ve Render sır taşımaz).
- Sırlar `SecretStr`; günlüğe, hata iletisine, `repr`'e **asla** yazılmaz (BYOK dahil).
- `.env.example` yalnız adları içerir. Gerçek değerler sır yöneticisinden ortam değişkeni veya dosya olarak enjekte edilir; imaj içinde sır yok.
- Kaynakta kimlik bilgileri kullanıcı dizininde (`~/.config/kaynak-proje/google-api.json`, `backlinks-api.json`) `[K: CLAUDE.md]`; çok kiracılı sistemde uygun değil, kiracı başına şifreli DB kaydı (belge 04 `byok_keys`).
- CI'da **gizli bilgi taraması** (kaynakta `secret-scan` işi var `[doğrulandı: ci.yml]`).

### 6.2 Ortam değişkenleri (taslak)

| Ad | Amaç | Gizli | Servisler | Varsayılan |
|---|---|---|---|---|
| `SEOA_ENV` | `dev`/`test`/`staging`/`prod` | – | tümü | `dev` |
| `SEOA_LOG_LEVEL` | günlük düzeyi | – | tümü | `INFO` |
| `SEOA_DATABASE_URL` | PostgreSQL bağlantısı | ✅ | api, control, analyze, llm, report | – |
| `SEOA_REDIS_URL` | kuyruk, limit, pub/sub | ✅ | tümü (ACL'li) | – |
| `SEOA_OBJECT_STORE_ENDPOINT/BUCKET` | nesne depolama | – | api, control, analyze, llm, report, fetch*, render* | – |
| `SEOA_OBJECT_STORE_ACCESS_KEY/SECRET_KEY` | depolama kimliği | ✅ | yukarıdakiler (fetch/render: **yalnız-yazma**, `staging/` ön ekli anahtar) `[?]` FS1 | – |
| `SEOA_KMS_KEY_ID` | BYOK zarf şifreleme anahtarı | ✅ | llm, api (şifreleme) | – |
| `SEOA_LLM_API_KEY` | platform LLM anahtarı | ✅ | **yalnız llm** | – |
| `SEOA_LLM_MODEL_DEFAULT` / `_DEEP` | model adları (yapılandırma, koda gömülü değil) | – | llm | – |
| `SEOA_LLM_BUDGET_*` | varsayılan token/maliyet tavanı | – | llm, control | plana göre |
| `SEOA_PSI_API_KEY` | PageSpeed/CrUX anahtarı | ✅ | **yalnız fetch** (sabit hedefli çağrı) | – |
| `SEOA_EGRESS_PROXY_URL` | çıkış vekili | ✅ (kimlik içerirse) | fetch, render | – |
| `SEOA_BOT_USER_AGENT` | `SEOAnalyzerBot/1.0 (+https://…/bot)` | – | fetch, render | – (D10) |
| `SEOA_FETCH_MAX_PAGE_BYTES` | sayfa gövdesi sınırı | – | fetch | `10485760` `[K: MAX_PAGE_BYTES]` |
| `SEOA_FETCH_MAX_REDIRECTS` | redirect sınırı | – | fetch | `5` `[K: fetch_page max_redirects]` |
| `SEOA_FETCH_TIMEOUT_S` / `_WALL_TIMEOUT_S` | istek / duvar saati süresi | – | fetch | `30` / `45` |
| `SEOA_RENDER_TIMEOUT_MS` | render süresi | – | render | `15000` `[K: render_page]` |
| `SEOA_RENDER_MAX_CONCURRENCY` | eşzamanlı bağlam | – | render | `2` |
| `SEOA_QUOTA_*` | plan kotaları | – | api, control | plana göre |
| `SEOA_SESSION_SECRET` | oturum imzası | ✅ | api | – |
| `SEOA_CORS_ORIGINS` | izinli kaynaklar | – | api | boş |
| `SEOA_OTEL_ENDPOINT`, `SEOA_SENTRY_DSN` | izleme | ✅ (DSN) | tümü | boş |

`*` Fetch/render DB'ye **erişmez** ve nesne depolamada yalnız yazma yetkisi alır; sonuçları Redis akışı + depolama üzerinden control worker'a verir. Belge 02 bu ayrımı varsaymıştı ama yazım yolunu tanımlamamıştı **(açık karar FS1)**.

## 7. Test dizini düzeni

### 7.1 Dizin

```
tests/
├── conftest.py
├── unit/                 # saf çekirdek: checks/, scoring/, parse/, crawl/, render/, schemagen/, facts/
├── golden/               # sabit girdi → sabit findings+score JSON
├── hostile/              # ssrf/, parsing/, llm/ (düşmanca girdi)
├── parity/               # kaynakla karşılaştırma (§7.3)
├── integration/          # Postgres+Redis, pipeline, çökme/lease, nezaket
├── e2e/                  # compose yığını: API → rapor
├── architecture/         # test_purity.py, import sözleşmeleri, sürüm/hash tutarlılığı
└── fixtures/             # HTML/header/robots/sitemap örnekleri
```

İşaretler: `@pytest.mark.network` (varsayılan **atlanır**; kaynak CI'da `NETWORK_TESTS` ortam değişkeniyle yalnız 3.11 bacağında açıyor `[doğrulandı: ci.yml]`), `@pytest.mark.slow`, `@pytest.mark.requires_services`.

### 7.2 Fixture konvansiyonu ve kaynağın gerçeği
Kaynak `tests/fixtures/` içinde **yalnız iki dosya** var (`dataforseo_mcp_2_8_10_tools.txt`, `lighthouse_agentic_13_5_psi.json`) `[doğrulandı]`. `test_page_checks.py`'nin başlığı: *"Her kontrol id'si için bir POSITIVE ve bir NEAR_MISS sayfası; temiz taban sayfa hiçbir şey üretmemeli. Tüm HTML satır içi, hiçbir test ağa dokunmaz"* `[doğrulandı]`. Yani **hazır bir fixture kütüphanesi yok**, belge 01 §13.1 ve belge 09 Faz 0'daki "kaynak fixture'larını yükle" ifadeleri bu haliyle uygulanamaz: fixture'lar test dosyalarından **çıkarılmalıdır** (§7.3).

Adlandırma: `tests/fixtures/pages/<alan>-<kural-id>-<positive|near-miss|clean>.html` + `.headers.json` (örn. `page-missing-title-positive.html`). Beklenen çıktı golden dizininde.

### 7.3 Parity koşucusu (belge 00 §4) `[B]`

```
third_party/kaynak_proje/            # cca7e4a'ya sabitli, salt-okunur kopya (scripts/, hooks/, data/)
scripts/extract_parity_cases.py    # kaynak test dosyalarından satır içi HTML/header örneklerini çıkarır
tests/parity/
  cases/*.yaml                     # {id, url, headers, html, kaynak_test, beklenen_kaynak_çıktısı}
  test_page_checks_parity.py       # kaynak run_checks ↔ bizim checks: {id, severity, count} eşit mi
  expected_diffs.yaml              # bilinçli farklar + gerekçe (örn. Türkçe'de kapalı 2 kontrol)
```

- **Diferansiyel test:** aynı girdi kaynak `page_checks` (alt süreç/izole içe aktarma) ve bizim implementasyonla çalıştırılır; bulgu kümeleri (`id`, `severity`, `count`) karşılaştırılır. Kaynak CLI dosya girdisini destekler (`_from_file(path, base_url, headers_json)` `[doğrulandı]`).
- **Beklenen farklar** kayıtlıdır; kayıtsız fark = test hatası.
- **Anlık görüntü yenileme** manuel iş akışıyla (`parity-refresh.yml`): yeni commit çekilir, vakalar yeniden çıkarılır, fark raporu insan incelemesine sunulur.
- Kaynağın dışında kalan modüller (transport, sitemap, drift) için aynı yaklaşım: ya diferansiyel ya da **kaynak testin uyarlanmış kopyası** `tests/unit/` altında.

### 7.4 SSRF testleri için gerçek durum (belge 00 §4, belge 09 §4 ile ilgili uyarı)
Önceki belgeler "kaynağın `test_url_safety*.py` + `test_hostile_inputs.py` testleri yeni resolver'a karşı aynen çalışır" varsaydı. Kaynak kontrolü iki şeyi değiştirir:

1. **`test_hostile_inputs.py` bir SSRF testi değildir.** İçeriği (19 test): iç içe katalog/JSON derinliği, `keywordseverywhere` bozuk gövdeleri, Lighthouse okuyucusu, UCP profili, `robots.txt` satır ayırıcı kenar durumları, tohumlu şekil fuzz'ı `[doğrulandı: test adları]`. SSRF kapsamı `test_url_safety.py` (72), `test_url_safety_ipv6.py` (45), `test_url_safety_port_pin.py` (14) içindedir.
2. **SSRF testleri `socket.getaddrinfo` monkeypatch'ine bağlıdır:** `_pin_dns|getaddrinfo` geçişi `test_url_safety.py`'de 90, `_ipv6`'da 54, `_port_pin`'de 15; Playwright route/handler geçişi `test_url_safety.py`'de 20 `[doğrulandı: grep sayımı]`. Bu testler `SafeResolver`'a karşı **değişmeden çalışmaz**. `test_url_safety_port_pin.py` ise `LOCAL_TARGETS` izin listesini sınar (belge 00 L1: **taşınmaz**).

Bizim yaklaşımımız: **politika testleri** (`is_safe_ip`, `validate_url_strict` sonuçları, authority-confusion, engelli hostname, DNS64, çoklu A/AAAA) taşınır ama `getaddrinfo` yamasının yerine `tests/hostile/ssrf/conftest.py` içinde **`FakeResolver` enjeksiyonu** konur; **pin/yarış testleri** yeni resolver davranışına göre yeniden yazılır (belge 09 P1); yerel-hedef izin listesi testleri atlanır. Bu, belge 09 §4.1 teslimat 0.3'ün "aynen çalışır halde" ifadesini **"adaptörle taşınmış"** olarak değiştirir.

### 7.5 Golden, integration, e2e
- **Golden:** `tests/golden/<vaka>/{page.html, headers.json, expected/findings.json, expected/scores.json}`; her beklenen dosya `rule_version`/`score_version` taşır. Yenileme `scripts/regen_golden.py --reason "<gerekçe>"` (gerekçesiz çalışmaz; fark PR'da görünür).
- **Integration:** gerçek PostgreSQL + Redis (CI servisi), sahte HTTP hedefi; çökme/lease, fan-in yarışı, nezaket testleri (belge 02 §17).
- **E2E seam sorunu `[?]` FS2:** SSRF politikası özel IP'yi reddeder; yerel bir test sitesi de özel IP'dedir. Kaynak bu ihtiyacı `LOCAL_TARGETS` ile çözer, biz o mekanizmayı kaldırdık. Öneri: e2e'de `safefetch.Fetcher` **protokolü** üzerinden `FixtureFetcher` enjekte edilir (aynı arayüz, sabit içerik); SSRF politikası ayrıca hostile testlerle doğrulanır. Prod kodunda "test modu izin listesi" bulunmaz.

## 8. Alembic ve tohum veri

```
migrations/
├── alembic.ini
├── env.py                       # async engine, hedef metadata = seoa.db.models
└── versions/
    ├── 0001_core_tenancy.py     # tenants, users, sites
    ├── 0002_audits_pipeline.py  # audits, audit_stages, audit_pages, page_fetches
    ├── 0003_findings_scores.py  # findings, not_checked, category_scores, audit_scores, rule_versions, score_versions, reports
    ├── 0004_rls.py              # RLS politikaları (belge 04)
    ├── 0005_llm_qa_usage.py     # Faz 2b: llm_calls, llm_cache, advisory_scores, qa_*, usage_ledger, byok_keys
    └── 0006_monitoring.py       # Faz 3: site_verifications, monitoring_schedules, drift_baselines, drift_events
```

| Kural | Gerekçe |
|---|---|
| Ardışık numara + açıklayıcı ad | Sıra açık; birleştirme çakışması erken görünür |
| **İleri-yalnız (forward-only) üretimde**, geliştirmede geri alınabilir (`downgrade`) | Üretim geri alması veri kaybı riskidir |
| Yıkıcı değişiklik iki adım (ekle → taşı → kaldır) | Sıfır kesinti dağıtımı (belge 02 §16) |
| RLS politikaları göç içinde ve testli | Kiracı izolasyonu kod incelemesinden kaçmasın |
| CI: `upgrade head → downgrade base → upgrade head` temiz PostgreSQL'de | Göç zinciri bozulmasın |
| Tablolar faza göre gelir (belge 04 faz tablosu) | Faz 1 yalnız ihtiyaç duyduğunu taşır |

**Tohum:** `python -m seoa.cli seed-rules` **idempotent**; `data/rules/*.json` hash'lerini okur, yoksa `rule_versions`/`score_versions` satırı ekler, varsa dokunmaz. Dev tohumu (`data/seed/`): örnek kiracı, kullanıcı, API anahtarı. **Üretimde dev tohumu çalışmaz** (`SEOA_ENV=prod` ise reddeder).

Tablo listesi belge 04 sözleşmesine göredir; belge 04'te sapma olursa bu dosya düzeltilir **(doğrulanmadı: belge 04 henüz yazılıyor)**.

## 9. Nesne depolama düzeni

```
tenants/{tenant_id}/audits/{audit_id}/
├── pages/{page_id}/
│   ├── body.html.zst            # ham HTML (≤ 10 MiB, belge 05 §6.1)
│   ├── headers.json             # yanıt başlıkları + redirect zinciri
│   ├── rendered.html.zst        # yalnız render edilen sayfalar
│   └── extracted.json           # çıkarılmış metin ve yapı özeti (LLM girdisi)
├── artifacts/
│   ├── robots.txt
│   └── sitemaps/{n}.xml.zst
└── report/
    ├── audit.json               # nihai rapor (belge 06 şeması)
    ├── report.html
    └── report.pdf               # Faz 3
staging/{audit_id}/{shard}/...   # fetch/render worker'larının yalnız-yazma alanı (FS1); control doğrulayıp taşır
```

| Kural | Gerekçe |
|---|---|
| Anahtar bileşenleri **yalnız UUIDv7** (kullanıcı/siteden gelen dize yok) | Yol gezinme (path traversal) ve çakışma yok |
| Anahtar kiracıyla başlar; IAM/ön ek politikası kiracıya bağlanabilir | İzolasyon |
| Sıkıştırma `zstd` `[B, kütüphane doğrulanmadı]`; `sha256` ve bayt boyutu `page_fetches.body_ref` ile DB'de | Bütünlük, boyut izleme |
| **Etiketler:** `class=page-body\|rendered\|extracted\|artifact\|report\|pdf`, `retention=30d\|90d\|permanent` | Yaşam döngüsü kuralları etiketle çalışır |
| Varsayılan saklama: sayfa gövdeleri 30 gün, rapor ve JSON süresiz (belge 04 `[?]`) | Yeniden skorlama penceresi vs maliyet/gizlilik |
| Kiracı silme isteği: `tenants/{tenant_id}/` önekinin tamamı silinir; DB satırları belge 04 sürecine göre | KVKK/GDPR `[?]` |
| Rapor indirmeleri **imzalı, kısa ömürlü URL** ile (belge 06) | Doğrudan nesne erişimi yok |
| Sunucu tarafı şifreleme açık; BYOK anahtarları **nesne depolamada tutulmaz** (DB'de zarf şifreli) | Sır ayrımı |
| Aynı gövde için çapraz-kiracı tekilleştirme **yok** | Bir kiracının başka birinin sitesini denetlediğini sızdırmamak |

## 10. Adlandırma konvansiyonları

| Konu | Kural | Örnek |
|---|---|---|
| Kural/kontrol id'si | kebab-case, kaynakla **aynı** (parity için) | `missing-title`, `canonical-points-elsewhere` |
| Yeni kural id'si | aynı biçim; asla yeniden kullanılmaz, silinen id "emekli" olarak kalır | `html-over-2mb` |
| Paket/modül/fonksiyon | `snake_case` | `js_gap.py`, `rate_metric()` |
| Sınıf | `PascalCase` | `SafeResolver`, `AuditJSON` |
| Sabit | `UPPER_SNAKE` | `MAX_PAGE_BYTES` |
| Ortam değişkeni | `SEOA_` + `UPPER_SNAKE` | `SEOA_REDIS_URL` |
| Kuyruk | `q_<tür>` | `q_fetch` (belge 02 §3.1) |
| DB tablo/kolon | `snake_case`, çoğul tablo | `audit_pages`, `rule_version` |
| Migration | `NNNN_<slug>.py` | `0003_findings_scores.py` |
| Veri dosyası | `kebab-case.json` | `quality-gates.json` |
| Nesne anahtarı | §9 | |
| Fixture | `<alan>-<id>-<tür>.html` | `page-noindex-near-miss.html` |

**Enum sözlüğü** (belge 04 sözleşmesi; değerler kodda `domain/` içinde **tek kaynaktır**, DB `CHECK`, Pydantic ve OpenAPI buradan üretilir):

| Enum | Değerler |
|---|---|
| `audit.mode` | `site`, `page` |
| `audit.status` | `queued`, `running`, `partial`, `completed`, `failed`, `canceled` |
| `stage` | `validate`, `fetch_entry`, `robots`, `discovery`, `sample`, `fetch_pages`, `render`, `measure`, `score`, `advise`, `synthesize`, `report` |
| `stage.status` | `pending`, `running`, `done`, `skipped`, `failed` |
| `layer` | `A`, `B`, `C` |
| `severity` | `Critical`, `High`, `Medium`, `Low`, `Info` |
| `category` | `technical`, `onpage`, `content`, `schema`, `performance`, `ai_readiness`, `images` |
| `sample_kind` | `core`, `exploration` |
| `tier` | `unverified`, `verified` |

Not: kaynak severity sıralaması `("Critical","High","Medium","Low")` dört değerlidir `[doğrulandı: page_checks.SEVERITY_ORDER]`; `Info` bizim eklememizdir (belge 01 §6).

## 11. Dağıtım dosyaları

```
deploy/
├── docker/
│   ├── Dockerfile               # çok aşamalı; hedefler: api, control, fetch, render, analyze, llm, report
│   └── entrypoints/             # worker türü başına başlatma betiği
├── compose/
│   └── docker-compose.dev.yml   # api, control, fetch, render, analyze, llm, report, postgres, redis, minio, egress-proxy
├── egress/
│   ├── README.md                # ağ modeli ve doğrulama
│   └── acl/                     # deny-private.conf: RFC1918, 127/8, 169.254/16, 100.64/10, ::1, fc00::/7, fe80::/10, metadata ana bilgisayarları
└── k8s/                         # NetworkPolicy (egress yalnız vekile), dağıtımlar (Faz 2a)
```

| Karar | Detay |
|---|---|
| **Tek çok-aşamalı Dockerfile, worker başına hedef** `[B]` (FS5) | Katman paylaşımı + en az bağımlılık: `render` Chromium taşır, `llm` yalnız sağlayıcı SDK ve şifre çözme, `analyze` `lxml`/ayrıştırıcılar, `fetch` `aiohttp`; BYOK şifre çözme kütüphanesi yalnız `llm` imajında |
| Güvenlik | root olmayan kullanıcı, salt-okunur kök dosya sistemi, gereksiz yetenekler düşürülmüş, imajda sır yok; `render` için ek sandbox profili `[?]` (P3 çıktısı) |
| **Ağ bölgeleri** (belge 02 §3.1) | `internal` ağı (DB, Redis, depolama, analyze, llm, report, control) ve `egress` ağı (fetch, render → vekil → internet); `egress`'ten `internal`'a yol yok |
| Egress vekili | Ürün seçimi açık `[?]` FS7 (ör. Squid veya Envoy). ACL'ler `deploy/egress/acl/`. **Uygulama içi `SafeResolver`'a ek ve bağımsız son savunma** (belge 05 §5.3); bu katman olmadan render üretime çıkmaz |
| Dev sınırı | Docker köprü ağlarında özel aralık engeli prod'u birebir yansıtmaz; **prod benzeri doğrulama staging'de** egress testiyle yapılır (belge 09 Faz 2a çıkış kriteri) |
| Sağlık | her servis `/healthz` (canlılık) ve `/readyz` (hazır: DB/Redis erişimi) |
| Kapanış | `SIGTERM`'de yeni iş alma durur, süren iş biter veya lease'e bırakılır (belge 02 §16) |

## 12. Belge ve ADR düzeni

```
docs/
├── architecture/        # güncel tasarım (bu belgeler): "sistem şu an böyle olmalı"
├── adr/                 # tekil kararlar: "şu tarihte şunu şu nedenle seçtik"
│   ├── 0000-template.md
│   ├── 0001-python-stack.md
│   ├── 0002-safe-resolver-instead-of-getaddrinfo-patch.md
│   ├── 0003-score-computed-by-code.md
│   ├── 0004-core-and-exploration-samples.md
│   └── 0005-queue-technology.md        # Faz 0 P2 sonrası
└── kaynak analizi notları   # kaynak analizi (değişmez referans)
```

ADR şablonu (`docs/adr/0000-template.md`):

```markdown
# NNNN. <Karar başlığı>

- Durum: Önerildi | Kabul | Reddedildi | Yerine geçildi (NNNN)
- Tarih: YYYY-MM-DD
- Karar verenler: <roller>
- İlgili belgeler: architecture/NN-..., ADR NNNN

## Bağlam
Hangi sorun, hangi kısıtlar, hangi veriler (kaynak/ölçüm bağlantılı).

## Karar
Tek net cümle + gerekçe.

## Alternatifler
Değerlendirilen seçenekler ve neden seçilmediği.

## Sonuçlar
Olumlu, olumsuz, açılan yeni kararlar; geri dönüş maliyeti.

## Doğrulama
Nasıl kanıtlanacak (prototip, test, ölçüm) ve ne zaman gözden geçirilecek.
```

Kurallar: mimari belgeden **sapan** bir uygulama kararı **önce** ADR + ilgili mimari belge güncellemesi, sonra kod (belge 09 §12). Karar günlüğü (belge 10) ADR'lere bağlanan indekstir. Numaralar yeniden kullanılmaz, yerine geçilen ADR silinmez.

## 13. CI iş akışları ve kapılar

### 13.1 Kaynaktaki CI `[doğrulandı: .github/workflows/ci.yml]`
İşler: `lint` (syntax + `ruff check`, ruff **0.17.1 sabit**), `test` (Python 3.11/3.12/3.14 matrisi, `pip install -r requirements.txt pytest`), `secret-scan`, `portability` (OS matrisi), `dep-audit` (`pip-audit`, Python matrisi). Eylemler **commit SHA'sına sabitlenmiş** (`# v7.0.1` yorumlu). Ruff: `select = ["E","F","W","I"]`, `ignore = ["E501"]`, satır 100, hedef `py311`. `CODEOWNERS`, `dependabot.yml` mevcut. Ek dosyalar: `v2.yml`, `windows-smoke.yml` (içerikleri okunmadı, **doğrulanmadı**).

### 13.2 Bizim iş akışlarımız `[B]`

```
.github/workflows/
├── ci.yml              # her PR ve main
├── release.yml         # imaj derleme (hedef başına), etiketleme
└── parity-refresh.yml  # manuel: third_party anlık görüntüsünü yenile, vakaları çıkar, fark raporu
```

`ci.yml` işleri ve **zorunlu kapılar** (PR birleştirme koşulu):

| İş | Ne yapar | Zorunlu |
|---|---|---|
| `lint` | `ruff check` + `ruff format --check` (sürüm sabit) | ✅ |
| `typecheck` | `mypy` (saf çekirdekte `strict`, diğerlerinde kademeli) | ✅ |
| `architecture` | `import-linter` + `tests/architecture` (saflık AST testi, veri hash↔sürüm) | ✅ |
| `unit` | `tests/unit` + `tests/golden`, Python 3.11 ve 3.12 | ✅ |
| `hostile` | `tests/hostile` (ayrı iş, hızlı geri bildirim) | ✅ |
| `parity` | `tests/parity` (`third_party/` anlık görüntüsüne karşı) | ✅ |
| `integration` | PostgreSQL + Redis servisleri, `tests/integration` | ✅ |
| `migrations` | `upgrade head → downgrade base → upgrade head` | ✅ |
| `secret-scan` | izlenen dosyalarda sır taraması `[K]` | ✅ |
| `dep-audit` | `pip-audit` `[K]` | ✅ (yüksek önem) |
| `e2e` | compose yığını (`FixtureFetcher`), gece + sürüm öncesi | ⛔ PR'da zorunlu değil |
| `network` | `-m network` testleri, yalnız bir Python bacağında `[K]` | ⛔ |

Python matrisi: kaynak 3.11/3.12/3.14 kullanıyor `[doğrulandı]`; biz **3.11 (taban) ve 3.12** ile başlarız, 3.14 `[?]` (FS8: bağımlılıkların desteğine göre). Windows/macOS taşınabilirlik işi **yok**: ürün Linux konteynerlerinde çalışır (kaynağın `portability` işi plugin kurulumu içindi).

Diğer: eylemler SHA'ya sabit `[K]`; `pre-commit` (ruff, biçim, sır tarama) yerelde aynı kuralları çalıştırır; `CODEOWNERS` `safefetch/`, `checks/`, `scoring/`, `data/rules/`, `migrations/` için zorunlu inceleme ister (güvenlik ve skor değişiklikleri tek kişinin kararı olmasın).

## 14. Doğrulama matrisi (kaynak ↔ bu belge)

| İddia | Kontrol | Sonuç |
|---|---|---|
| `scripts/*.py` 63 dosya, 32 340 satır | `ls *.py \| wc -l`, `wc -l` toplamı | ✅ |
| Faz gruplarının satır toplamı (5 083+4 320+1 181+680+7 345+1 749+11 982 = 32 340) | betikle toplandı | ✅ |
| Kaynak commit `cca7e4a2…` (2026-11-11) | `git log -1` | ✅ |
| `requires-python >=3.11`, ruff `py311`, satır 100, `select E,F,W,I` | `pyproject.toml` | ✅ |
| `data/` yalnız `google-updates.json` (66 güncelleme, 6 unverified, `last_verified 2026-11-10`) | dosya okundu | ✅ |
| `tests/fixtures/` yalnız 2 dosya | `ls fixtures` | ✅ |
| `test_page_checks.py`: POSITIVE/NEAR_MISS, satır içi HTML, ağ yok; 43 test | dosya başlığı + sayım | ✅ |
| `test_hostile_inputs.py` SSRF değil (agentic/JSON/lighthouse/robots şekilleri) | 19 test adı okundu | ✅ **önceki belgelerle çelişir (§7.4)** |
| SSRF testleri `getaddrinfo`/`_pin_dns`'e bağlı (90/54/15 geçiş) | `grep -c` | ✅ |
| `test_url_safety_port_pin.py` yerel-hedef izin listesini sınar | test adları (`allowed_local_target…`) | ✅ |
| Drift SQLite şeması (`baselines`, `comparisons`, kolonlar, WAL, yol) | `drift_baseline.py:95-135` | ✅ |
| `drift_compare` 17 kural (8/6/3), `google_auth.validate_url` import eder | belge 01 §12 + `drift_compare.py:29-37` | ✅ |
| `drift_history`, `drift_report`, `analyze_visual`, `keyword_planner`, `youtube_search`, `release_sign`, `verify_release` için ada göre test bulunamadı | `tests/*.py` taraması | ✅ (tarama adla eşleşme; dolaylı test olabilir) |
| `parse_html`, `fetch_page`, `render_page`, `sitemap_discovery`, `transport_check` `url_safety`'den import eder | satır taraması | ✅ |
| `page_checks.THRESHOLDS` 13 anahtar; `STOPWORDS` yalnız İngilizce | `page_checks.py:124-138, 236` | ✅ |
| `hooks/validate-schema.py` 371 satır; 9 köşeli parantez placeholder + `REPLACE` regex; ReDoS önlemli tag ayrıştırıcısı | dosya okundu | ✅ |
| `schema_generate` 4 üretici (`reservation`, `order_action`, `discussion`, `profile`) | `def` listesi | ✅ |
| `ci.yml` işleri, ruff 0.17.1, SHA sabitleme, secret-scan, dep-audit | dosya okundu | ✅ |
| `sitemap_discovery` sınırları (50 MiB, 50 000, 16, 50, 20) | `:63-80` | ✅ |

**Doğrulanmadı / bu turda okunmadı:** import-linter'ın stdlib modüllerini yasaklayabildiği ve `include_external_packages` sözdizimi; ruff `TID251` dizin bazlı kullanımı; `pydantic-settings`/`zstd` kütüphane sürümleri; `transport_check.py`'nin toplama/değerlendirme ayrılabilirliği; `content_quality.py` içinde kalıp listesi–algoritma sınırı; `schema/templates.json`'un hangi koddan okunduğu; `v2.yml`/`windows-smoke.yml` içerikleri; belge 04 tablo listesinin bu belgedeki göç sırasıyla birebir uyumu (belge 04 yazılıyor); `last_verified` test eşiği.

## 15. Açık kararlar

| # | Karar | Öneri | Not |
|---|---|---|---|
| **FS1** | Fetch/render worker'ları DB'ye erişmesin; sonuçları yalnız-yazma depolama + Redis akışıyla iletsin, DB'ye control yazsın | Evet | Belge 02 §3.1 ile uyumlu; yazım yolu belge 02/04'te tanımlanmalı |
| **FS2** | E2E için `FixtureFetcher` protokol enjeksiyonu (prod'da test izin listesi yok) | Evet | §7.5 |
| **FS3** | `third_party/kaynak_proje/` kopya mı submodule mu | **Sabitlenmiş kopya** + `NOTICE` | Submodule ağ/bağımlılık karmaşası; kopya tekrarlanabilir |
| **FS4** | Tek paket (`seoa`) + servis başına giriş noktası, mi çoklu paket (uv workspace) mi | **Tek paket** (Faz 0-2) | Basitlik; sınırlar import-linter ile zorlanır, gerekirse sonra bölünür |
| **FS5** | Tek çok-aşamalı Dockerfile mı, worker başına ayrı Dockerfile mı | **Tek, çok hedefli** | §11 |
| **FS6** | Mesaj kataloğu (`i18n`) paket içinde mi veri dizininde mi | Paket içinde (`report/i18n/`) | Sürümle birlikte dağıtım |
| **FS7** | Egress vekili ürünü | Faz 0 P3'te seçilir | Squid/Envoy vb. değerlendirilecek |
| **FS8** | Python matrisi | 3.11 + 3.12; 3.14 bağımlılıklara göre | Kaynak 3.14 de test ediyor |
| **FS9** | Kural verisi biçimi: JSON mu YAML mı | **JSON** + JSON Schema | Kaynakla aynı, makine doğrulaması; yorum ihtiyacı `_doc` alanıyla |
| **FS10** | Saflık zorlaması: yalnız import-linter mı, AST testiyle birlikte mi | **İkisi birden** | §3.3 |
| **FS11** | Belge 09 §4.1 teslimat 0.3 ("SSRF testleri yeni resolver'a karşı yeşil") ifadesinin düzeltilmesi: "politika testleri adaptörle taşınmış; pin testleri yeniden yazılmış" | Evet | §7.4; Faz 0 çıkış kriteri bu yeni tanıma göre yazılmalı |
| D10, D8, D11, D12, D13 | (önceki belgelerden) | Önerilerle ilerlenir | Belge 10'da toplanır |

## 16. Sonraki belgeler

| Belge | Konu | Bu belgeden devraldığı |
|---|---|---|
| `03-rubrik-and-prompts.md` | LLM rubrikleri ve prompt'ları | `llm/prompts/`, `llm/rubrics/` dizinleri, B8 kuralı |
| `04-data-model.md` | Tablolar, DDL, RLS, saklama | Enum sözlüğü (§10), göç sırası (§8), nesne anahtarları (§9) |
| `06-io-schemas.md` | API ve `audit.json` şeması | `report/schema.py`, `api/schemas/`, i18n anahtarları |
| `07-features.md` | Özellik kataloğu ve faz eşlemesi | Portlama haritası (§4) |
| `09-implementation-roadmap.md` | Faz planı | §4 faz atamaları, FS11 düzeltmesi, Faz 0 teslimatları |
| `10-decision-log.md` | Karar günlüğü | FS1-FS11 |
