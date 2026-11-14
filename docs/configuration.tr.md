# Yapılandırma (`.env`)

[English](configuration.md) · **Türkçe**

Hiçbiri zorunlu değildir. Hangisi eksikse yalnızca ilgili bölüm "ölçülmedi" der ve nedenini yazar. Hangi bağlantının hazır olduğunu uygulamada **Ayarlar › Bağlantılar** sayfasından görür ve **Test et** düğmesiyle sınarsınız.

| Değişken | Ne işe yarar | Nereden alınır |
|---|---|---|
| `ANTHROPIC_API_KEY` | Özet, öneriler, E-E-A-T yorumu ve **Sohbet** | [console.anthropic.com](https://console.anthropic.com/) |
| `SEOA_GOOGLE_API_KEY` | Gerçek kullanıcı hız verisi (CrUX) ve PageSpeed | Google Cloud › Credentials › API key (aşağıya bakın) |
| `SEOA_OPENPAGERANK_KEY` | Alan adı otoritesi tahmini | [keywordseverywhere.com/account/openpagerank](https://keywordseverywhere.com/account/openpagerank) (ücretsiz anahtar tek bir IP'ye bağlıdır) |
| `SEOA_LLM_MODEL` | Kullanılan model (varsayılan `claude-haiku-5-5`) | |
| `SEOA_LLM_BUDGET_USD` | Bu kurulumun toplam yapay zekâ harcama tavanı (varsayılan 8) | |
| `SEOA_MAX_PAGES` | Site denetiminde örneklem sayfa sayısı (varsayılan 25) | |
| `SEOA_RENDER` | `0` yazarsanız tarayıcıyla render kapanır | |
| `SEOA_DATA_DIR` | Veritabanı ve dosyaların yeri (varsayılan `./data`) | |

`.env` ve `data/` klasörü `.gitignore` içindedir; anahtarlarınız ve Google belirteçleriniz depoya girmez.

## Google bağlantısı

İki ayrı şey vardır:

1. **Tek bir API anahtarı** (CrUX ve PageSpeed için, site sahipliği gerekmez): Google Cloud'da bir proje açın, *Chrome UX Report API* ve *PageSpeed Insights API*'yi etkinleştirin, **Credentials › Create credentials › API key** ile anahtar üretin, iki API ile kısıtlayın ve `SEOA_GOOGLE_API_KEY` olarak `.env`'e yazın.
2. **Search Console** (kendi siteniz için indeksleme, sorgular, sıralama): salt okunur OAuth ile bağlanır.
   1. Aynı projede *Google Search Console API*'yi etkinleştirin.
   2. OAuth onay ekranını **External / Testing** olarak kurun ve kendi e-postanızı *Test users* listesine ekleyin.
   3. **Desktop app** türünde bir OAuth istemcisi oluşturup JSON'u `data/google_client.json` olarak kaydedin.
   4. Uygulamayı başlatın, **Ayarlar › Bağlantılar › Google ile bağlan** düğmesine basın.
   5. Sitenin hesabınızda doğrulanmış bir Search Console mülkü olmalıdır (en kolayı *Alan* mülkü).

Ayrıntılar ve sık görülen hatalar: [`docs/google-setup.tr.md`](google-setup.tr.md). Durumu komut satırından görmek için: `python scripts/google_setup_check.py`.
