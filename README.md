<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/Zero_Dependencies-stdlib_only-success?style=for-the-badge" alt="Zero Dependencies">
  <img src="https://img.shields.io/badge/GitHub_Actions-Automated-2088FF?style=for-the-badge&logo=githubactions&logoColor=white" alt="GitHub Actions">
  <img src="https://img.shields.io/badge/GitHub_Pages-Live-222222?style=for-the-badge&logo=githubpages&logoColor=white" alt="GitHub Pages">
</p>

# IPTV Auto Stack

An automated pipeline that collects channels from multiple public IPTV sources, health-checks every stream, deduplicates entries, and generates clean M3U playlists with a web portal — deployed to GitHub Pages on a 6-hour schedule.

## How It Works

```
┌─────────────┐    ┌───────────┐    ┌───────────┐    ┌──────────────┐
│  1. FETCH   │───▶│ 2. CLASS. │───▶│ 3. SCORE  │───▶│ 4. DEDUPE    │
│  9 sources  │    │ country + │    │ pre-score │    │ + fallbacks  │
│  ~4700 URLs │    │ category  │    │ by weight │    │ ~600 unique  │
└─────────────┘    └───────────┘    └───────────┘    └──────┬───────┘
                                                           │
┌─────────────┐    ┌───────────┐    ┌───────────┐          │
│  7. OUTPUT  │◀───│ 6. TIER   │◀───│ 5. CHECK  │◀─────────┘
│  m3u/portal │    │ strict vs │    │ tiered L0 │
│  + reports  │    │ relaxed   │    │ to L3     │
└─────────────┘    └───────────┘    └───────────┘
```

### Pipeline Stages

| Stage | What it does |
|-------|-------------|
| **Fetch** | Downloads M3U/M3U8 playlists from 9 configured sources in parallel |
| **Classify** | Assigns each channel a country (AZ, TR, RU, EN, other) and categories (sport, cinema, news, kids) using tvg-id suffixes, keywords, TLDs, and source tags |
| **Pre-Score** | Ranks channels by source weight, HTTPS preference, and metadata quality — before any health checks |
| **Smart Dedupe** | Groups channels by normalized name, picks the best-scored URL as primary, and retains up to 4 alternate URLs as fallbacks |
| **Health Check** | Probes only the deduplicated set (~600 URLs instead of ~4700) with a tiered approach. If the primary URL fails, fallback URLs are tried automatically |
| **Tier & Output** | Generates two playlist tiers and a web portal |

### Tiered Health Checking

Instead of a binary alive/dead check, each URL is probed through graduated levels:

| Level | What is verified | Tier |
|-------|-----------------|------|
| **L0** | Connection failed, 4xx/5xx, or denied payload | Dead |
| **L1** | HTTP 200 OK, valid response | Relaxed |
| **L2** | Playlist parsed, child URI also returns 200 | Strict |
| **L3** | Media segment is reachable and valid | Strict |

- **Strict playlist** — Only L2+ channels (fully verified stream pipeline)
- **Relaxed playlist** — L1+ channels (more channels, slightly less certainty)

### Fallback Mechanism

When a channel appears in multiple sources with different URLs, the pipeline keeps backup URLs. If the primary URL fails health-check, alternates are tried automatically — maximizing channel retention without sacrificing reliability.

## Live URLs

After GitHub Pages deployment, these URLs are always up-to-date:

| Playlist | URL |
|----------|-----|
| All channels (relaxed) | `https://emahmudov.github.io/iptv-stack/all.m3u` |
| All channels (strict) | `https://emahmudov.github.io/iptv-stack/strict/all.m3u` |
| By country (grouped) | `https://emahmudov.github.io/iptv-stack/by-country/all.m3u` |
| Azerbaijan only | `https://emahmudov.github.io/iptv-stack/by-country/az.m3u` |
| Turkey only | `https://emahmudov.github.io/iptv-stack/by-country/tr.m3u` |
| Russia only | `https://emahmudov.github.io/iptv-stack/by-country/ru.m3u` |
| English only | `https://emahmudov.github.io/iptv-stack/by-country/en.m3u` |
| Sport | `https://emahmudov.github.io/iptv-stack/by-category/sport.m3u` |
| Cinema | `https://emahmudov.github.io/iptv-stack/by-category/cinema.m3u` |
| Web Portal | `https://emahmudov.github.io/iptv-stack/portal/index.html` |

> Add the `all.m3u` URL to any IPTV player (VLC, TiviMate, OTT Navigator, etc.) — it refreshes every 6 hours automatically.

## Project Structure

```
iptv-stack/
├── .github/
│   └── workflows/
│       └── build-and-deploy.yml   # GitHub Actions: build every 6h + deploy to Pages
├── config/
│   ├── sources.json               # IPTV source URLs, weights, and tags
│   ├── profile.json               # Timeouts, workers, grouping rules, tier config
│   └── overrides.json             # Manual country/category fixes for specific channels
├── src/iptv_stack/
│   ├── __main__.py                # CLI entry point (build / serve commands)
│   ├── models.py                  # StreamEntry and Source data models
│   ├── fetch.py                   # Parallel M3U source downloader
│   ├── m3u.py                     # M3U parser and renderer
│   ├── classify.py                # Country and category classification engine
│   ├── check.py                   # Tiered health checker with fallback support
│   ├── pipeline.py                # Main pipeline orchestrator
│   └── portal.py                  # HTML portal generator
├── scripts/
│   ├── build.sh                   # Build wrapper script
│   └── serve.sh                   # Local HTTP server script
└── dist/                          # Generated output (gitignored)
    ├── all.m3u                    # Main playlist (relaxed tier)
    ├── channels.json              # Full channel data as JSON
    ├── build-report.json          # Build statistics and source report
    ├── strict/                    # Strict tier playlists
    │   ├── all.m3u
    │   ├── by-country/
    │   └── by-category/
    ├── by-country/
    │   ├── all.m3u                # All channels grouped by country name
    │   ├── az.m3u
    │   ├── tr.m3u
    │   ├── ru.m3u
    │   └── en.m3u
    ├── by-category/
    │   ├── sport.m3u
    │   ├── cinema.m3u
    │   ├── news.m3u
    │   └── kids.m3u
    ├── portal/
    │   └── index.html             # Web UI with search, filters, and tier info
    └── reports/
        ├── verification-report.json
        ├── failed-channels.json
        └── group-audit.json
```

## Quick Start

### Prerequisites

- Python 3.9+ (no pip packages required — stdlib only)

### Local Build

```bash
git clone https://github.com/emahmudov/iptv-stack.git
cd iptv-stack
./scripts/build.sh
```

### Local Server

```bash
./scripts/serve.sh 8080
```

Then open:
- Playlist: `http://127.0.0.1:8080/all.m3u`
- Portal: `http://127.0.0.1:8080/portal/index.html`

### GitHub Pages Deployment

The repository includes a GitHub Actions workflow that:

1. Runs `./scripts/build.sh` on every push to `main`
2. Runs automatically every 6 hours via cron schedule
3. Deploys the `dist/` output to GitHub Pages

**First-time setup:**
1. Go to your repo → **Settings** → **Pages**
2. Set Source to **GitHub Actions**
3. Go to **Actions** tab → **Build And Deploy IPTV** → **Run workflow**

After the first successful run, your playlists will be live at the URLs listed above.

## Configuration

### `config/sources.json`

Defines the IPTV sources to fetch. Each source has a name, URL, weight (priority), and tags:

```json
{
  "sources": [
    {
      "name": "iptv-org-country-az",
      "url": "https://iptv-org.github.io/iptv/countries/az.m3u",
      "enabled": true,
      "weight": 100,
      "tags": ["az"]
    }
  ]
}
```

- **weight** (0–100): Higher weight = preferred during deduplication
- **tags**: Used for country/category classification fallback
- **enabled**: Set to `false` to skip a source without removing it

### `config/profile.json`

Controls pipeline behavior:

```json
{
  "healthcheck": {
    "timeout_seconds": 12,
    "workers": 50,
    "retries": 2,
    "max_fallbacks": 3
  },
  "tiers": {
    "strict_min_level": 2,
    "relaxed_min_level": 1
  },
  "channel_selection": {
    "prefer_https": true,
    "keep_per_channel": 1,
    "max_fallback_urls": 4
  }
}
```

### `config/overrides.json`

Manual fixes for channels that are misclassified by the automatic engine:

```json
{
  "by_name": {
    "CBC Sport": { "country": "az", "categories": ["sport"] },
    "ITV Deportes": { "country": "other", "categories": ["sport"] }
  },
  "by_url": {}
}
```

## Reports

After each build, detailed reports are generated in `dist/reports/`:

| Report | Description |
|--------|-------------|
| `verification-report.json` | Total channels per tier, failure reason breakdown |
| `failed-channels.json` | Every failed channel with error details |
| `group-audit.json` | Country/category distribution, full AZ channel list |

## Automation (Cron)

For local automatic builds every 6 hours:

```bash
crontab -e
```

Add:

```cron
0 */6 * * * cd /path/to/iptv-stack && ./scripts/build.sh >> dist/cron.log 2>&1
```

## Tech Stack

- **Language:** Python 3.9+ (zero external dependencies)
- **CI/CD:** GitHub Actions
- **Hosting:** GitHub Pages
- **Health Check:** Tiered HTTP probing with retry and fallback
- **Concurrency:** `ThreadPoolExecutor` for parallel fetch and health checks

## Important Notes

- This tool is intended for use with streams you have the right to access.
- Health checks use standard HTTP requests — no stream decoding is performed.
- Build time depends on the number of sources and network conditions; tune `workers` and `timeout_seconds` in `profile.json` if needed.
- The `dist/` directory is gitignored — it is generated fresh by each build and deployed via GitHub Actions.

## License

This project is for personal use. Use responsibly and only with content you are authorized to access.
