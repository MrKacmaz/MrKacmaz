#!/usr/bin/env python3
"""Render a neofetch-style terminal card (SVG) with live GitHub stats.

Runs daily in .github/workflows/profile.yml, which publishes it to the `output` branch.
Local run:
    GITHUB_TOKEN=$(gh auth token) python3 scripts/neofetch.py [out.svg]
Only the standard library is used.
"""

import calendar
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

USER = os.environ.get("GH_USER", "MrKacmaz")
TOKEN = os.environ["GITHUB_TOKEN"]
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/neofetch.svg")

# ── edit me ──────────────────────────────────────────────────────────────────
PROMPT = "alperen@kacmaz"

INFO = [
    ("OS", "macOS (dev) · Linux (prod)"),
    ("Host", "Tarfin Labs · agrifintech"),
    ("Kernel", "Software Engineer"),
    ("Uptime", "{uptime}"),
    ("Location", "Denizli, Türkiye"),
    ("IDE", "PhpStorm, VS Code, Xcode"),
    ("Terminal", "Warp + zsh + Claude Code"),
    None,
    ("Languages.Code", "PHP, TypeScript, C#, Python, Swift"),
    ("Stack.Backend", "Laravel, Pest, Horizon, Reverb"),
    ("Stack.Frontend", "Vue 3, Nuxt, React, Astro, Tailwind"),
    ("Stack.Mobile", "React Native, Expo"),
    ("Stack.GameDev", "Unity, BepInEx, Blender"),
    ("Stack.Infra", "Docker, AWS, Firebase, Actions"),
    None,
    "Contact",
    ("Email", "alperen703.akm@gmail.com"),
    ("LinkedIn", "in/alperen-kacmaz-2202"),
    ("Web", "mrkacmaz.com"),
    None,
    "GitHub Stats",
    (("Repos", "{repos}"), ("Followers", "{followers}")),
    (("Contributions (1y)", "{year}"), ("All-time", "{total}")),
    (("Streak", "{streak}"), ("Longest", "{longest}")),
]

NOW = [
    "shipping agrifintech @ tarfin",
    "modding Graveyard Keeper 2",
    "building an idle tycoon in Unity",
    "writing a macOS menu-bar app",
]

# every █ becomes a pixel block (drawn as rects, so it does not depend on the viewer's font)
MONOGRAM = [
    " █████  ██   ██",
    "██   ██ ██  ██ ",
    "███████ █████  ",
    "██   ██ ██  ██ ",
    "██   ██ ██   ██",
]
# ─────────────────────────────────────────────────────────────────────────────

WIDTH = 920
COLS = 58  # characters in the info column
HEAT_WEEKS = 22
LEVELS = {
    "NONE": "#161b22",
    "FIRST_QUARTILE": "#0e4429",
    "SECOND_QUARTILE": "#006d32",
    "THIRD_QUARTILE": "#26a641",
    "FOURTH_QUARTILE": "#39d353",
}
PALETTE = ["#f85149", "#e3b341", "#39d353", "#56d4dd", "#58a6ff", "#bc8cff", "#ff7b72", "#e6edf3"]


def graphql(query, variables=None):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        body = json.load(res)
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch():
    user = graphql(
        """query($login: String!) {
          user(login: $login) {
            createdAt
            followers { totalCount }
            repositories(ownerAffiliations: OWNER, privacy: PUBLIC) { totalCount }
            contributionsCollection {
              contributionCalendar {
                totalContributions
                weeks { contributionDays { date contributionCount contributionLevel } }
              }
            }
          }
        }""",
        {"login": USER},
    )["user"]

    # contributionsCollection spans at most one year, so ask for each year separately.
    first = int(user["createdAt"][:4])
    years = range(first, dt.date.today().year + 1)
    aliases = "\n".join(
        f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z") '
        "{ contributionCalendar { weeks { contributionDays { date contributionCount } } } }"
        for y in years
    )
    history = graphql(f'query($login: String!) {{ user(login: $login) {{ {aliases} }} }}', {"login": USER})["user"]

    days = {}
    for year in history.values():
        for week in year["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                days[day["date"]] = day["contributionCount"]
    return user, dict(sorted(days.items()))


def uptime(since):
    today = dt.date.today()
    months = (today.year - since.year) * 12 + today.month - since.month
    if today.day < since.day:
        months -= 1
    year, month = divmod(since.month - 1 + months, 12)
    year += since.year
    anchor = dt.date(year, month + 1, min(since.day, calendar.monthrange(year, month + 1)[1]))
    years, months = divmod(months, 12)
    days = (today - anchor).days
    plural = lambda n, word: f"{n} {word}{'' if n == 1 else 's'}"
    return ", ".join([plural(years, "year"), plural(months, "month"), plural(days, "day")])


def streaks(days):
    today = dt.date.today().isoformat()
    counts = [(d, c) for d, c in days.items() if d <= today]
    longest = run = 0
    for _, count in counts:
        run = run + 1 if count else 0
        longest = max(longest, run)
    # today still counts as "in progress", so an empty today does not break the streak
    if counts and counts[-1][1] == 0:
        counts = counts[:-1]
    current = 0
    for _, count in reversed(counts):
        if not count:
            break
        current += 1
    return current, longest


def leader(key, value, width):
    dots = max(width - len(key) - len(value) - 3, 1)
    return [("k", key + ":"), ("d", " " + "." * dots + " "), ("v", value)]


def tspans(parts):
    return "".join(f'<tspan class="{cls}">{escape(text)}</tspan>' for cls, text in parts)


def render(user, days):
    current, longest = streaks(days)
    cal = user["contributionsCollection"]["contributionCalendar"]
    values = {
        "uptime": uptime(dt.date.fromisoformat(user["createdAt"][:10])),
        "repos": str(user["repositories"]["totalCount"]),
        "followers": str(user["followers"]["totalCount"]),
        "year": f'{cal["totalContributions"]:,}',
        "total": f"{sum(days.values()):,}",
        "streak": f"{current} day{'' if current == 1 else 's'}",
        "longest": f"{longest} days",
    }

    lh, top = 20, 104
    left_x, right_x = 32, 376
    halves = (30, COLS - 3 - 30)

    right = [f'<text x="{right_x}" y="{top}" class="r" style="animation-delay:.9s">'
             f'<tspan class="u">{PROMPT.split("@")[0]}</tspan><tspan class="v">@</tspan>'
             f'<tspan class="u">{PROMPT.split("@")[1]}</tspan></text>',
             f'<text x="{right_x}" y="{top + lh}" class="r d" style="animation-delay:.94s">{"─" * COLS}</text>']
    y = top + lh * 2
    for i, row in enumerate(INFO):
        delay = f"animation-delay:{0.98 + i * 0.04:.2f}s"
        if isinstance(row, str):
            title = f"─ {row} "
            right.append(f'<text x="{right_x}" y="{y}" class="r" style="{delay}">'
                         f'<tspan class="h">{escape(title)}</tspan><tspan class="d">{"─" * (COLS - len(title))}</tspan></text>')
        elif isinstance(row, tuple) and isinstance(row[0], tuple):
            (k1, v1), (k2, v2) = row
            parts = leader(k1, v1.format(**values), halves[0]) + [("d", " | ")] + leader(k2, v2.format(**values), halves[1])
            right.append(f'<text x="{right_x}" y="{y}" class="r" style="{delay}">{tspans(parts)}</text>')
        elif row:
            key, value = row
            right.append(f'<text x="{right_x}" y="{y}" class="r" style="{delay}">'
                         f'{tspans(leader(key, value.format(**values), COLS))}</text>')
        y += lh
    end = 0.98 + len(INFO) * 0.04

    y += 6
    blocks = "".join(f'<rect x="{right_x + i * 30}" y="{y}" width="26" height="14" rx="2" fill="{c}"/>'
                     for i, c in enumerate(PALETTE))
    right.append(f'<g class="r" style="animation-delay:{end:.2f}s">{blocks}</g>')
    bottom = y + 14

    # left column: monogram, ~/.now, contribution heatmap
    cw, ch, mono_top = 12, 22, top - 14
    mono_w, mono_h = max(map(len, MONOGRAM)) * cw, len(MONOGRAM) * ch
    pixels = [(left_x + x * cw, mono_top + y * ch) for y, line in enumerate(MONOGRAM)
              for x, char in enumerate(line) if char == "█"]
    left = [
        '<g fill="#0e4429">' + "".join(f'<rect x="{x + 4}" y="{y + 4}" width="{cw}" height="{ch}"/>' for x, y in pixels) + "</g>",
        '<g fill="url(#g)">' + "".join(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}"/>' for x, y in pixels) + "</g>",
        f'<rect x="{left_x}" y="{mono_top}" width="{mono_w + 4}" height="{mono_h + 4}" fill="url(#scan)"/>',
    ]
    ly = mono_top + mono_h + 40
    left.append(f'<text x="{left_x}" y="{ly}"><tspan class="p">~/.now</tspan></text>')
    for i, line in enumerate(NOW):
        left.append(f'<text x="{left_x}" y="{ly + (i + 1) * lh}"><tspan class="k">▸</tspan> '
                    f'<tspan class="v">{escape(line)}</tspan></text>')

    ly += (len(NOW) + 1) * lh + 22
    left.append(f'<text x="{left_x}" y="{ly}"><tspan class="p">~/.contributions</tspan>'
                f'<tspan class="d"> --last {HEAT_WEEKS}w</tspan></text>')
    weeks = cal["weeks"][-HEAT_WEEKS:]
    cells = []
    for wx, week in enumerate(weeks):
        for day in week["contributionDays"]:
            dy = dt.date.fromisoformat(day["date"]).isoweekday() % 7
            cells.append(f'<rect class="c" style="animation-delay:{0.95 + wx * 0.03:.2f}s" '
                         f'x="{left_x + wx * 14}" y="{ly + 12 + dy * 14}" width="11" height="11" rx="2" '
                         f'fill="{LEVELS[day["contributionLevel"]]}"><title>{day["date"]}: {day["contributionCount"]}</title></rect>')
    left.append("".join(cells))
    legend_y = ly + 12 + 7 * 14 + 16
    legend = "".join(f'<rect x="{left_x + 40 + i * 14}" y="{legend_y - 10}" width="11" height="11" rx="2" fill="{c}"/>'
                     for i, c in enumerate(LEVELS.values()))
    left.append(f'<text x="{left_x}" y="{legend_y}" class="d">less</text>{legend}'
                f'<text x="{left_x + 40 + 5 * 14 + 4}" y="{legend_y}" class="d">more</text>')

    prompt_y = max(bottom, legend_y) + 42
    height = prompt_y + 28
    user_part, host_part = PROMPT.split("@")
    after_prompt = left_x + (len(PROMPT) + 4) * 8.4  # 8.4px ≈ one 14px monospace column

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" role="img" aria-label="neofetch: {escape(PROMPT)}">
<title>{escape(PROMPT)} — neofetch</title>
<defs>
  <linearGradient id="g" gradientUnits="userSpaceOnUse" x1="{left_x}" y1="{mono_top}" x2="{left_x + mono_w}" y2="{mono_top + mono_h}">
    <stop offset="0" stop-color="#39d353"/><stop offset="1" stop-color="#56d4dd"/>
  </linearGradient>
  <pattern id="scan" width="4" height="3" patternUnits="userSpaceOnUse">
    <rect width="4" height="1" fill="#0d1117" opacity=".55"/>
  </pattern>
</defs>
<style>
  text {{ font: 14px 'JetBrains Mono', 'Fira Code', 'Cascadia Code', SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace; fill: #e6edf3; white-space: pre; }}
  .u {{ fill: #39d353; font-weight: 700; }}
  .p {{ fill: #58a6ff; font-weight: 700; }}
  .k {{ fill: #39d353; }}
  .v {{ fill: #e6edf3; }}
  .d {{ fill: #484f58; }}
  .h {{ fill: #56d4dd; font-weight: 700; }}
  .t {{ fill: #8b949e; font-size: 13px; }}
  .r, .c, .left, .end {{ opacity: 0; animation: in .2s ease-out forwards; }}
  .left {{ animation-delay: .9s; }}
  .end {{ animation-delay: {end + 0.2:.2f}s; }}
  .typed {{ animation: type .6s steps(8) .3s forwards; }}
  .cursor {{ animation: blink 1s steps(1) infinite; }}
  @keyframes in {{ to {{ opacity: 1; }} }}
  @keyframes type {{ to {{ transform: translateX(67.2px); }} }}
  @keyframes blink {{ 50% {{ opacity: 0; }} }}
  @media (prefers-reduced-motion: reduce) {{
    .r, .c, .left, .end {{ opacity: 1; animation: none; }}
    .typed {{ display: none; }}
  }}
</style>
<rect x=".5" y=".5" width="{WIDTH - 1}" height="{height - 1}" rx="12" fill="#0d1117" stroke="#30363d"/>
<path d="M.5 12.5a12 12 0 0 1 12-12h{WIDTH - 25}a12 12 0 0 1 12 12V36H.5z" fill="#161b22"/>
<line x1="0" y1="36.5" x2="{WIDTH}" y2="36.5" stroke="#30363d"/>
<circle cx="22" cy="18" r="6" fill="#f85149"/><circle cx="42" cy="18" r="6" fill="#e3b341"/><circle cx="62" cy="18" r="6" fill="#39d353"/>
<text x="{WIDTH / 2}" y="23" text-anchor="middle" class="t">{escape(user_part)}@{escape(host_part)}: ~ — zsh</text>
<text x="{left_x}" y="68"><tspan class="u">{escape(PROMPT)}</tspan><tspan class="v">:</tspan><tspan class="p">~</tspan><tspan class="v">$</tspan></text>
<text x="{after_prompt}" y="68">neofetch</text>
<rect class="typed" x="{after_prompt}" y="52" width="72" height="22" fill="#0d1117"/>
<g class="left">
{chr(10).join(left)}
</g>
{chr(10).join(right)}
<g class="end">
<text x="{left_x}" y="{prompt_y}"><tspan class="u">{escape(PROMPT)}</tspan><tspan class="v">:</tspan><tspan class="p">~</tspan><tspan class="v">$</tspan></text>
<rect class="cursor" x="{after_prompt}" y="{prompt_y - 14}" width="9" height="18" fill="#39d353"/>
</g>
</svg>
'''


def main():
    user, days = fetch()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(user, days), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
