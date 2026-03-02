# IPTV Auto Stack

`IPTV Auto Stack` manual playlist yığımı azaltmaq üçün hazırlanmış local pipeline-dır.

Nə edir:

- Birdən çox `m3u/m3u8` source-dan kanalları toplayır.
- Stream URL-ləri health-check edir.
- Duplicate kanalları score ilə seçib təmizləyir.
- Country və category üzrə qruplaşdırıb yeni playlist-lər yaradır.
- Sadə portal generasiya edir (`dist/portal/index.html`).

## Qovluq strukturu

```text
iptv-stack/
  config/
    sources.json
    profile.json
    overrides.json
  src/iptv_stack/
  scripts/
    build.sh
    serve.sh
  dist/
```

## İstifadə

```bash
cd /Users/elvin/Desktop/projects/iptv-stack
./scripts/build.sh
./scripts/serve.sh 8080
```

Sonra brauzerdə aç:

- `http://127.0.0.1:8080/portal/index.html`
- Əsas playlist: `http://127.0.0.1:8080/all.m3u`

## Avtomatlaşdırma (cron)

Hər 6 saatda avtomatik build üçün:

```bash
crontab -e
```

Bu sətri əlavə et:

```cron
0 */6 * * * cd /Users/elvin/Desktop/projects/iptv-stack && ./scripts/build.sh >> /Users/elvin/Desktop/projects/iptv-stack/dist/cron.log 2>&1
```

## Konfiqurasiya

- `config/sources.json`: source URL-lər, prioritet (`weight`), tag-lər.
- `config/profile.json`: timeout, health-check, grouping rules.
- `config/overrides.json`: manual düzəlişlər (kanal adı/url üzrə).

## Vacib qeydlər

- Bu alət yalnız istifadə etməyə hüququn olan stream-lər üçün nəzərdə tutulub.
- `drop_dead_streams=true` olduqda işləməyən URL-lər playlist-dən çıxarılır.
- Source çox olduqda build vaxtı arta bilər; `healthcheck.max_urls` və `workers` parametrlərini tənzimlə.
