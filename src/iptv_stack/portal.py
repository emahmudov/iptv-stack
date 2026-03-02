from __future__ import annotations

from pathlib import Path
import json


def build_portal(channels_json_path: Path, output_html_path: Path, title: str) -> None:
    channels = json.loads(channels_json_path.read_text(encoding="utf-8"))
    payload = json.dumps(channels, ensure_ascii=False)
    output_html_path.parent.mkdir(parents=True, exist_ok=True)
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    :root {{
      --bg: #0f172a;
      --panel: #111827;
      --panel-2: #1f2937;
      --text: #f8fafc;
      --muted: #cbd5e1;
      --accent: #22d3ee;
      --accent-2: #84cc16;
      --danger: #fb7185;
      --border: #334155;
      --radius: 14px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background:
        radial-gradient(1200px 700px at -10% -20%, #164e63 0%, transparent 60%),
        radial-gradient(1000px 800px at 110% -10%, #365314 0%, transparent 55%),
        linear-gradient(160deg, #020617 0%, #0f172a 45%, #111827 100%);
      font-family: "Space Grotesk", "Segoe UI", sans-serif;
      padding: 24px;
    }}
    .wrap {{
      max-width: 1280px;
      margin: 0 auto;
      animation: rise 400ms ease-out;
    }}
    @keyframes rise {{
      from {{ opacity: 0; transform: translateY(8px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    .hero {{
      background: linear-gradient(130deg, rgba(34, 211, 238, 0.18), rgba(132, 204, 22, 0.12));
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px;
      margin-bottom: 16px;
      backdrop-filter: blur(6px);
    }}
    .hero h1 {{
      margin: 0 0 8px;
      font-size: clamp(24px, 4vw, 34px);
      letter-spacing: 0.4px;
    }}
    .hero p {{
      margin: 0;
      color: var(--muted);
      font-size: 15px;
    }}
    .controls {{
      display: grid;
      grid-template-columns: 1fr repeat(2, minmax(150px, 220px));
      gap: 10px;
      margin-bottom: 14px;
    }}
    input, select {{
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: rgba(15, 23, 42, 0.85);
      color: var(--text);
      padding: 10px 12px;
      font-size: 14px;
    }}
    .stats {{
      margin: 8px 0 14px;
      color: var(--muted);
      font-size: 13px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: rgba(17, 24, 39, 0.84);
    }}
    th, td {{
      padding: 11px 10px;
      text-align: left;
      border-bottom: 1px solid rgba(51, 65, 85, 0.8);
      font-size: 13px;
      vertical-align: top;
    }}
    th {{
      background: rgba(15, 23, 42, 0.9);
      position: sticky;
      top: 0;
    }}
    tr:hover td {{
      background: rgba(30, 41, 59, 0.65);
    }}
    .chip {{
      display: inline-block;
      background: rgba(34, 211, 238, 0.15);
      color: #a5f3fc;
      border: 1px solid rgba(34, 211, 238, 0.3);
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 11px;
      margin-right: 6px;
      margin-bottom: 4px;
    }}
    a {{
      color: #a5f3fc;
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    .button {{
      color: #022c22;
      background: #34d399;
      border: 0;
      border-radius: 8px;
      padding: 6px 10px;
      font-size: 12px;
      cursor: pointer;
      font-weight: 700;
    }}
    .button[disabled] {{
      cursor: not-allowed;
      background: #334155;
      color: #94a3b8;
    }}
    .footer-links {{
      margin: 14px 0;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .footer-links a {{
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 6px 10px;
      background: rgba(15, 23, 42, 0.7);
      color: #e2e8f0;
      font-size: 12px;
    }}
    @media (max-width: 840px) {{
      body {{ padding: 14px; }}
      .controls {{
        grid-template-columns: 1fr;
      }}
      th:nth-child(3), td:nth-child(3) {{
        display: none;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>{title}</h1>
      <p>Auto-generated playlist portal. Filter channels by name, country and category.</p>
    </section>
    <div class="controls">
      <input id="search" type="search" placeholder="Search channel..." />
      <select id="countryFilter">
        <option value="">All countries</option>
      </select>
      <select id="categoryFilter">
        <option value="">All categories</option>
      </select>
    </div>
    <div class="footer-links">
      <a href="../all.m3u">Download all.m3u</a>
      <a href="../by-country/az.m3u">AZ list</a>
      <a href="../by-country/tr.m3u">TR list</a>
      <a href="../by-country/ru.m3u">RU list</a>
      <a href="../by-country/en.m3u">EN list</a>
      <a href="../by-category/sport.m3u">Sport list</a>
      <a href="../by-category/cinema.m3u">Cinema list</a>
    </div>
    <div class="stats" id="stats"></div>
    <div style="overflow:auto; max-height: 68vh;">
      <table>
        <thead>
          <tr>
            <th style="width: 28%;">Name</th>
            <th style="width: 10%;">Country</th>
            <th style="width: 16%;">Category</th>
            <th style="width: 18%;">Source</th>
            <th style="width: 16%;">Stream</th>
            <th style="width: 12%;">Health</th>
          </tr>
        </thead>
        <tbody id="rows"></tbody>
      </table>
    </div>
  </div>
  <script>
    const CHANNELS = {payload};
    const rowsEl = document.getElementById("rows");
    const statsEl = document.getElementById("stats");
    const searchEl = document.getElementById("search");
    const countryEl = document.getElementById("countryFilter");
    const categoryEl = document.getElementById("categoryFilter");

    const countries = [...new Set(CHANNELS.map((c) => c.country).filter(Boolean))].sort();
    const categories = [...new Set(CHANNELS.flatMap((c) => c.categories || []).filter(Boolean))].sort();
    countries.forEach((value) => {{
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = value.toUpperCase();
      countryEl.appendChild(opt);
    }});
    categories.forEach((value) => {{
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = value[0].toUpperCase() + value.slice(1);
      categoryEl.appendChild(opt);
    }});

    function copyUrl(url) {{
      navigator.clipboard.writeText(url).catch(() => {{}});
    }}

    function rowHtml(item) {{
      const tags = (item.categories || []).map((cat) => `<span class="chip">${{cat}}</span>`).join("");
      const healthy = item.alive === true ? "OK" : (item.alive === false ? "Fail" : "Unknown");
      const button = item.url ? `<button class="button" onclick="copyUrl('${{item.url.replace(/'/g, "\\\\'")}}')">Copy URL</button>` : `<button class="button" disabled>No URL</button>`;
      return `<tr>
        <td>${{item.name || "-"}}</td>
        <td>${{(item.country || "other").toUpperCase()}}</td>
        <td>${{tags}}</td>
        <td>${{item.source_name || "-"}}</td>
        <td><a href="${{item.url}}" target="_blank" rel="noreferrer">Open</a> ${{button}}</td>
        <td>${{healthy}}</td>
      </tr>`;
    }}

    function render() {{
      const q = searchEl.value.trim().toLowerCase();
      const country = countryEl.value;
      const category = categoryEl.value;

      const filtered = CHANNELS.filter((item) => {{
        if (q) {{
          const text = [item.name, item.group_title, item.source_name].join(" ").toLowerCase();
          if (!text.includes(q)) return false;
        }}
        if (country && item.country !== country) return false;
        if (category && !(item.categories || []).includes(category)) return false;
        return true;
      }});

      rowsEl.innerHTML = filtered.map(rowHtml).join("");
      statsEl.textContent = `Showing ${{filtered.length}} / ${{CHANNELS.length}} channels`;
    }}

    [searchEl, countryEl, categoryEl].forEach((el) => el.addEventListener("input", render));
    render();
  </script>
</body>
</html>
"""
    output_html_path.write_text(html, encoding="utf-8")
