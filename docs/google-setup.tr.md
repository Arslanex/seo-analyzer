# Google Search Console bağlantısı — kurulum kılavuzu

Bu uygulama Search Console verisini **salt okunur** (`webmasters.readonly`) izinle okur. Bir kez
Google Cloud'da OAuth istemcisi oluşturursunuz; sonra kendi Google hesabınızla bağlanırsınız.
Yalnızca yerel makinede (localhost) çalışır.

## 1. Google Cloud projesi

1. <https://console.cloud.google.com/> adresinde yeni bir proje oluşturun (ör. `seo-analyzer`).
2. **APIs & Services → Library** bölümünde **Google Search Console API**'yi bulup **Enable** deyin.

## 2. OAuth onay ekranı (test modu)

1. **APIs & Services → OAuth consent screen** (yeni arayüzde *Google Auth Platform*).
2. Kullanıcı türü: **External**. Uygulama adı ve e-posta alanlarını doldurun.
3. Yayın durumu **Testing** kalsın (yayınlamanıza gerek yok).
4. **Test users** listesine **kendi Google e-postanızı** ekleyin. Listede olmayan hesap bağlanamaz
   (`access_denied`).

## 3. OAuth istemcisi ("Desktop app")

1. **Credentials → Create credentials → OAuth client ID**.
2. Uygulama türü: **Desktop app**. Adı serbest.
3. **Download JSON** ile dosyayı indirin ve şu yola kaydedin:

   ```
   data/google_client.json
   ```

   (Başka bir yol için `SEOA_GOOGLE_CLIENT_FILE`; ya da dosya yerine
   `GOOGLE_OAUTH_CLIENT_ID` ve `GOOGLE_OAUTH_CLIENT_SECRET` ortam değişkenleri.)

Bu dosyayı paylaşmayın ve git'e eklemeyin; uygulama onu hiçbir yere yazdırmaz.

## 4. Bağlanma

1. Uygulamayı başlatın, tarayıcıda `http://127.0.0.1:<port>/connect/google` adresini açın
   (ya da arayüzdeki **Google ile bağlan** düğmesi).
2. Google'da hesabınızı seçin. "Bu uygulama Google tarafından doğrulanmadı" uyarısı normaldir
   (test modu): **Gelişmiş → (uygulama adı)'na git** deyin ve izni onaylayın.
3. Başarılıysa ana sayfaya `?google=connected` ile dönersiniz.

Durumu görmek için: `.venv/bin/python scripts/google_setup_check.py`

Bağlantıyı kesmek için arayüzdeki **Bağlantıyı kes** düğmesi (Google'daki izni de geri alır).

## 5. Mülk (property) ve site doğrulama

Denetlediğiniz sitenin Search Console'da **sizin hesabınızda doğrulanmış** bir mülkü olmalı.

- **Önerilen: Alan (Domain) mülkü** (`sc-domain:ornek.com`). Tüm alt alanları ve http/https'i
  kapsar. DNS TXT kaydıyla doğrulanır.
- URL öneki mülkü (`https://www.ornek.com/`) de çalışır; ama yalnızca tam o önek için geçerlidir.
- Doğrulama: Search Console → *Mülk ekle* → yönergeleri izleyin (DNS, HTML dosyası veya etiket).

Uygulama mülkü sizin yerinize **tahmin etmez**: denetlenen alan adıyla eşleşen mülk yoksa
"mülk bulunamadı" der ve başka bir sitenin verisini asla göstermez. `siteUnverifiedUser`
(doğrulanmamış) yetkisi sayılmaz.

## 6. Sık karşılaşılan hatalar

| Belirti | Neden / çözüm |
|---|---|
| `redirect_uri_mismatch` | İstemci türü "Desktop app" değil (ör. "Web application" seçilmiş). Masaüstü istemcisi oluşturup JSON'u yenileyin. |
| `access_denied` | Hesabınız OAuth ekranındaki **Test users** listesinde değil ya da izin ekranında reddettiniz. |
| `invalid_grant` | Erişim Google'dan geri alınmış ya da test modunda 7 günlük süre dolmuş. Uygulama kayıtlı anahtarı siler; **Google ile bağlan** ile yeniden bağlanın. |
| "Uygulama doğrulanmadı" uyarısı | Test modunda beklenen davranış; Gelişmiş → devam. |
| Yenileme anahtarı gelmedi | `myaccount.google.com/permissions` adresinden uygulamanın erişimini kaldırıp yeniden bağlanın. |
| Raporda "mülk bulunamadı" | Site için hesabınızda doğrulanmış mülk yok (bölüm 5). |
| Raporda "yetki yok" | Mülk var ama doğrulanmamış ya da hesabınızın izni yetersiz. |
| `rate-limited` | Google kota sınırı; URL Denetimi günde mülk başına 2000 sorgu. Bir süre sonra deneyin. |

Notlar: Search Console verisi 2-3 gün gecikmelidir; denetim bitiş tarihi bu yüzden bugünden 3 gün
öncesidir. Yenileme anahtarı `data/google_tokens.json` dosyasında (izin 0600) tutulur; bir ürün
için şifreli depolama gerekir.

## 7. İsteğe bağlı: tek API anahtarı (CrUX / PageSpeed)

Gerçek kullanıcı verisi (CrUX) ve PageSpeed için OAuth gerekmez; **tek bir API anahtarı** yeterlidir:

1. Aynı projede **Credentials → Create credentials → API key**.
2. **Chrome UX Report API** ve **PageSpeed Insights API**'yi etkinleştirin; anahtarı bu iki API ile
   kısıtlayın.
3. `.env` dosyasına ekleyin:

   ```
   SEOA_GOOGLE_API_KEY=...
   ```
