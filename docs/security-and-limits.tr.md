# Güvenlik, gizlilik ve sınırlar

[English](security-and-limits.md) · **Türkçe**

## Güvenlik ve gizlilik

- Kullanıcı adresleri tek bir istemciden geçer: özel IP, loopback ve metadata adresleri reddedilir; her yönlendirme ve render isteği doğrulanır.
- Anahtarlar yalnızca `.env` içinde durur; günlüklere, raporlara ve hata mesajlarına yazılmaz. Ayarlar sayfası anahtarı geri göstermez, yalnızca tanımlı olup olmadığını söyler.
- Güvenlik açığı bildirimi için [`SECURITY.md`](../SECURITY.md).

## Sınırlar

Tek kullanıcı, kimlik doğrulama yok, süreç içi kuyruk ve SQLite. Performans **lab** ölçümüdür (bu makineden); gerçek kullanıcı verisi için CrUX anahtarı gerekir, yeni ve az trafikli sitelerde Google veri vermez. Geri bağlantı verisi yoktur. Bilinen sınırların tam listesi [`CHANGELOG.md`](../CHANGELOG.md) içinde.
