# Mimari Belgeler: İndeks

> *English readers: these product design documents are written in Turkish. For the code layout and its rationale see [`../adr/0001-layered-architecture.md`](../adr/0001-layered-architecture.md).*

> **Kod yerleşimi için güncel kaynak** [`../adr/0001-layered-architecture.md`](../adr/0001-layered-architecture.md) belgesidir (dört katman: `domain`, `application`, `infrastructure`, `presentation`). Aşağıdaki belgeler ürünün tasarımını anlatır; içlerinde geçen dosya yolları (`checks/`, `report/`, `pipeline/` ...) uygulamadan önceki plandır.

Bir web sitesi girişi alıp skorlu ve kanıtlı rapor üreten SEO analiz ürününün mimarisi. Referans: MIT lisanslı bir açık kaynak proje (v2.6.0); atıf `NOTICE` dosyasındadır.

**Yığın:** Python ≥ 3.11 · FastAPI · PostgreSQL · Redis · Arq · aiohttp · Playwright · Pydantic v2. Kütüphane seçimleri Faz 0'da prototiple doğrulanır.

## Belgeler

| # | Dosya | Konu |
|---|---|---|
| 00 | [capability-parity](00-capability-parity.md) | kaynak projede olup bizde kaybolanlar, telafi kararları, gerileme güvencesi |
| 01 | [evaluation-system](01-evaluation-system.md) | Değerlendirme modeli: katmanlar (A/B/C), bulgu şeması, skor formülü, kapı, kapsam, güven |
| 02 | [agent-arhitecture](02-agent-arhitecture.md) | İş hattı, durum makinesi, worker'lar, kuyruk, bütçe, LLM katmanı, Q&A, izleme |
| 03 | [rubrik-and-prompts](03-rubrik-and-prompts.md) | Katman C rubrikleri, sinyal kataloğu, prompt'lar, doğrulayıcılar, bilinen yanlışlar |
| 04 | [data-model](04-data-model.md) | Tablolar, DDL, değiştirilemezlik, RLS, saklama |
| 05 | [system-design](05-system-design.md) | **I:** güvenli fetch, render, keşif, örneklem · **II:** bileşenler, güven bölgeleri, tehdit modeli, dağıtım |
| 06 | [io-schemas](06-io-schemas.md) | REST API, nihai `audit.json` şeması, rapor arayüzü |
| 07 | [features](07-features.md) | Özellik kataloğu, plan matrisi, non-feature'lar, bayraklar, metrikler |
| 08 | [file-structure](08-file-structure.md) | Depo ağacı, modül sınırları, **kaynak proje portlama haritası**, CI |
| 09 | [implementation-roadmap](09-implementation-roadmap.md) | Faz faz uygulama, çıkış kriterleri, prototipler |
| 10 | [decision-log](10-decision-log.md) | Tüm kararlar, durumları, bekleyen onaylar |
| 11 | [scoring-v2-and-site-analysis](11-scoring-v2-and-site-analysis.md) | Skor v2 (geçen kontrol payı), bağlantı/performans/görsel/indekslenebilirlik analizi, görünürlük sinyalleri |

> `02-agent-arhitecture.md` dosya adındaki yazım hatası (`arhitecture`) yer tutucudan gelir ve bilerek korunmuştur.

## Okuma sırası

1. **10** (neye karar verildi, neyin onayı bekleniyor)
2. **09** (ne sırayla yapılacak)
3. **01 → 03 → 02** (değerlendirme, LLM katmanı, çalıştırma)
4. **05 → 04 → 06** (sistem ve veri toplama, veri, yüzey)
5. **07 → 08** (özellikler, dosya yapısı)
6. **00** (kayıplar ve gerileme güvencesi)

## Konvansiyonlar

- `[K]` kaynak projeden alındı · `[B]` bizim kararımız · `[?]` açık karar · `[doğrulandı]` kaynak kodla veya dosyayla kontrol edildi.
- Dosya yolları aksi belirtilmedikçe `kaynak/` köküne göredir.
- Her belge sonunda **doğrulama matrisi** ve **açık kararlar** bölümü vardır; "doğrulanmadı" okunmayan veya belirsiz kalan noktaları gösterir.
- Karar kimlikleri belge önekiyle benzersizdir: `D`, `L`, `R`, `DM`, `IO`, `FT`, `FS`, `SD` (bkz. belge 10 §1).
- Enum ve tablo adları belge 04'teki sözleşmeyle aynıdır (`audit.status`, `stage`, `layer`, `severity`, `category`).
- Kaynaktan taşınan kodun telif ve atıf yükümlülüğü belge 00 §6'dadır.

## Durum

| Aşama | Durum |
|---|---|
| Mimari belgeler (00-10) | Taslak tamamlandı; onay bekleyen kararlar belge 10 §11'de |
| Uygulama | Başlamadı; **Faz 0** ile başlayacak (belge 09 §4) |
