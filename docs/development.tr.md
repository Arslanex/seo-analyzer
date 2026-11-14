# Geliştirme ve mimari

[English](development.md) · **Türkçe**

## Mimari

Kod dört katmana ayrılmıştır. **Bağımlılıklar yalnızca içe doğru akar**: iç katman, dıştakini bilmez.

```
presentation  ─▶  infrastructure  ─▶  application  ─▶  domain
 (HTTP, HTML)     (SQLite, HTTP,      (kullanım         (saf iş
                   tarayıcı, LLM,      senaryoları,      kuralları,
                   Google)             portlar)          modeller)
```

```
src/seoa/
├── config.py            ortam ayarları (.env)
├── bootstrap.py         bileşim kökü: somut sınıfları burada bağlar
├── domain/              saf iş kuralları, G/Ç yok
│   ├── models.py        varlıklar ve değer nesneleri
│   ├── rules/           kural kataloğu ve saf sayfa/schema kontrolleri
│   ├── scoring/         skor hesabı
│   ├── parsing/         HTML -> ParsedPage
│   ├── i18n/            Türkçe ve İngilizce metinler
│   └── urls.py, url_safety.py, text.py, ...
├── application/         kullanım senaryoları
│   ├── ports.py         dış dünyadan beklenenler (Protocol)
│   ├── audit/           iş hattı (orchestrator), servis, DTO'lar
│   ├── analysis/        links/, performance/, search_console/, modules/
│   ├── crawl/           keşif, örneklem, sitemap
│   ├── site/            robots.txt ve yapay zekâ tarayıcı erişimi
│   └── reporting/       AuditRecord -> AuditReport
├── infrastructure/      dış dünya
│   ├── http/            SSRF korumalı istemci, DNS çözücü, TLS/başlık sondaları
│   ├── persistence/     SQLite
│   ├── llm/             istemci, bütçe defteri, ajanlar, istemler
│   ├── integrations/    Google, CrUX, PSI, OpenPageRank, RDAP, Wayback ...
│   ├── rendering/       başsız tarayıcı
│   └── adapters.py      iş hattının dışarıya baktığı tek yüzey
└── presentation/
    ├── api/             FastAPI: routers/ (audits, reports, meta, home, audit_pages, settings)
    └── web/             Jinja şablonları, stiller, küçük betik
```

Kurallar `tests/architecture` ile otomatik denetlenir: katman yönü, import döngüsü yokluğu, `domain`'in hiçbir dış katmanı bilmemesi. Kararların gerekçesi: [`docs/adr/0001-layered-architecture.md`](adr/0001-layered-architecture.md). Ürün tasarımı belgeleri: [`docs/architecture/`](architecture/README.md).

**Yeni bir analiz modülü eklemek:** `application/analysis/modules/` altına bir dosya koyun, `register_module(...)` ile kaydedin ve `plugin.py` içindeki `MODULE_FILES` listesine adını ekleyin. Rapor bölümü `application/reporting/` altında okunur.

## Geliştirme

```bash
pytest -q                    # tüm testler (ağ ve yapay zekâ gerektirmez)
pytest tests/architecture    # katman kuralları
ruff check src tests scripts && ruff format --check src tests scripts
mypy                         # strict
```

Testler katmanları yansıtır: `tests/unit/{domain,application,infrastructure,presentation}`, uçtan uca `tests/e2e`.

Yapay zekâ ajanlarını gerçek API ile (yaklaşık 0,006 dolar) tek tek sınamak için: `python scripts/test_agents.py --agent all --budget 1`.
