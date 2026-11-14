# P1: `SafeResolver` doğrula-sonra-bağlan yarışını kapatıyor mu?

> Durum: **Tamamlandı (kısmi)** · Faz 0 · Kod: `seo-analyzer/src/seoa/safefetch/` · Testler: `seo-analyzer/tests/integration/test_p1_resolver_aiohttp.py`
> Sürümler: Python 3.12.16, aiohttp 3.14.5

## Soru ve ölçüt (belge 09 §4.2)
`aiohttp` için özel bir resolver, adresi **bağlantı anında** doğrulayarak kaynaktaki global `getaddrinfo` yamasının yerini tutabilir mi? Redirect hedefleri de geçiyor mu? TLS/SNI bozulmuyor mu?

## Yöntem
Yerel `aiohttp` sunucusu (127.0.0.1) + test amaçlı resolver'lar; her davranış bir test olarak kaydedildi (karakterizasyon testi). Gerçek DNS kullanılmadı.

## Bulgular

| # | Bulgu | Kanıt | Sonuç |
|---|---|---|---|
| 1 | `aiohttp` **bağlantıyı resolver'ın döndürdüğü IP'ye kurar**; `Host` başlığı özgün hostname olarak kalır | `test_connection_goes_to_the_resolver_address_and_host_header_is_kept` | ✅ Tasarımın temel varsayımı doğru: doğrulanan adres = bağlanılan adres |
| 2 | **`aiohttp` IP-literal URL'lerde resolver'ı HİÇ çağırmaz** (`http://127.0.0.1:port/` resolver'a uğramadan 200 döndü) | `test_ip_literal_urls_bypass_the_resolver_entirely` | ⚠️ **Yeni bulgu.** `SafeResolver` tek başına yetmez; IP-literal için `policy.check_url` zorunlu |
| 3 | Hostname → loopback çözülürse bağlantı engellenir ve sunucu **hiç istek görmez** | `test_safe_resolver_blocks_a_hostname_that_resolves_to_loopback` | ✅ |
| 4 | Metadata adları, obfuscated IPv4, FQDN-nokta lookup'tan **önce** engellenir | `test_blocked_names_and_literals_never_reach_lookup` (9 vaka) | ✅ |
| 5 | Rebinding: ilk çözümleme public, ikincisi private ise ikinci bağlantı reddedilir (her çözümleme yeniden yargılanır) | `test_rebinding_every_resolution_is_judged_again` | ✅ (resolver düzeyinde) |
| 6 | Hata türü `OSError` alt sınıfı olmalı, yoksa `ValueError` aiohttp'den sızar | `test_errors_are_oserrors_so_aiohttp_wraps_them` | ✅ (`class X(URLSafetyError, OSError)` çalışıyor) |
| 7 | Tüm A/AAAA kayıtları yargılanır; istenen aile yalnız IPv4 olsa bile private AAAA reddettirir | `test_refuses_mixed_records_even_if_caller_asked_for_ipv4_only` | ✅ |

## Tasarım sonucu (belgelere işlendi)

1. **İki katmanlı savunma zorunlu:** (a) her istek ve **her redirect adımı** için önce `policy.check_url` (IP-literal ve hostname kuralları), (b) hostname'ler için `SafeResolver` (bağlantı anında adres yargısı).
2. **Redirect'ler elle izlenir** (`allow_redirects=False`); her `Location` hedefi (a)'dan geçer. Kaynaktaki `requests` tabanlı akış bunu otomatik yapıyordu; `aiohttp`'ta bu bizim sorumluluğumuz.
3. Politika (`is_safe_ip`, engelli adlar, authority-confusion, DNS64) **saf modüldür**; kaynak test vektörleri (≈100 vaka) olduğu gibi taşındı ve geçiyor.

## Henüz doğrulanmadı (P1'in kalanı)
- **Gerçek TLS/SNI:** testler düz HTTP üzerinde. HTTPS'te sertifika doğrulamasının hostname'e göre yapıldığı (IP'ye değil) **gerçek bir HTTPS hedefiyle** doğrulanmalı; aiohttp belgeleri bunu söylüyor, biz ölçmedik.
- **Çok kayıtlı gerçek DNS, IPv6-only ortam, DNS64 ağı:** yalnız enjekte edilmiş lookup ile sınandı.
- **Redirect zinciri:** manuel redirect fetcher henüz yazılmadı (Faz 0 sonraki dilim).
- **Eşzamanlılık yükü:** global durum yok (kaynaktaki yama sorunu yok) ama yük altında ölçülmedi.
