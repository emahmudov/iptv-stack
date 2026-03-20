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
- Country all: `http://127.0.0.1:8080/by-country/all.m3u`
- Category all: `http://127.0.0.1:8080/by-category/all.m3u`

## Avtomatlaşdırma (cron)

Hər 6 saatda avtomatik build üçün:

```bash
crontab -e
```

Bu sətri əlavə et:

```cron
0 */6 * * * cd /Users/elvin/Desktop/projects/iptv-stack && ./scripts/build.sh >> /Users/elvin/Desktop/projects/iptv-stack/dist/cron.log 2>&1
```

## GitHub Actions + GitHub Pages (TV ucun en rahat yol)

Repo-da workflow var:

- `.github/workflows/build-and-deploy.yml`
- her `6 saatdan bir` ve manual run-da `./scripts/build.sh` isleyir
- `dist/` neticesini `GitHub Pages`-e deploy edir

Bir defe ac:

1. GitHub repo -> `Settings` -> `Pages`
2. `Source: GitHub Actions` sec
3. Sonra `Actions` bolmesinden `Build And Deploy IPTV` workflow-unu bir defe `Run workflow` et

Sabit URL formatlari:

- Playlist: `https://emahmudov.github.io/iptv-stack/all.m3u`
- Portal: `https://emahmudov.github.io/iptv-stack/portal/index.html`

## Konfiqurasiya

- `config/sources.json`: source URL-lər, prioritet (`weight`), tag-lər.
- `config/profile.json`: timeout, health-check, grouping rules.
- `config/overrides.json`: manual düzəlişlər (kanal adı/url üzrə).

## Dəqiqlik raportları

Build-dən sonra bunlara bax:

- `dist/reports/verification-report.json`: neçə kanal strict check-dən keçib, neçəsi düşüb, səbəb statistikası.
- `dist/reports/failed-channels.json`: düşən kanallar və texniki səbəbləri.
- `dist/reports/group-audit.json`: country/category bölgü statistikası və `AZ` kanallarının tam siyahısı.

## Vacib qeydlər

- Bu alət yalnız istifadə etməyə hüququn olan stream-lər üçün nəzərdə tutulub.
- `drop_dead_streams=true` olduqda işləməyən URL-lər playlist-dən çıxarılır.
- Source çox olduqda build vaxtı arta bilər; `healthcheck.max_urls` və `workers` parametrlərini tənzimlə.
