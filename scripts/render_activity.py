#!/usr/bin/env python3
"""Render a compact, privacy-safe GitHub profile overview as static SVG."""

from __future__ import annotations

import datetime as dt
import html
import json
import math
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request


GRAPHQL_URL = "https://api.github.com/graphql"


def graphql(token: str, query: str, variables: dict[str, str]) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-activity-renderer",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"GitHub GraphQL request failed ({error.code}): {detail}") from error
    if result.get("errors"):
        raise RuntimeError(f"GitHub GraphQL returned errors: {result['errors']}")
    return result["data"]


def streaks(counts: list[int]) -> tuple[int, int]:
    longest = 0
    run = 0
    for count in counts:
        run = run + 1 if count > 0 else 0
        longest = max(longest, run)

    current = 0
    for count in reversed(counts):
        if count == 0:
            break
        current += 1
    return current, longest


def render_svg(
    *,
    username: str,
    total: int,
    active_days: int,
    current_streak: int,
    longest_streak: int,
    public_repos: int,
    language_count: int,
    language_mix: list[tuple[str, str, float]],
    counts: list[int],
    start_weekday: int,
) -> str:
    positive = sorted(count for count in counts if count > 0)
    if positive:
        thresholds = [positive[min(len(positive) - 1, round((len(positive) - 1) * q))] for q in (.25, .5, .75)]
    else:
        thresholds = [1, 2, 3]
    heatmap_nodes = []
    for offset, count in enumerate(counts):
        position = start_weekday + offset
        column, row = divmod(position, 7)
        if count == 0:
            level = 0
        elif count <= thresholds[0]:
            level = 1
        elif count <= thresholds[1]:
            level = 2
        elif count <= thresholds[2]:
            level = 3
        else:
            level = 4
        heatmap_nodes.append(
            f'<rect x="{28 + column * 9}" y="{67 + row * 9}" width="7" height="7" rx="1.5" class="day l{level}" />'
        )

    def point(angle: float, radius: float = 48) -> tuple[float, float]:
        radians = math.radians(angle - 90)
        return 600 + radius * math.cos(radians), 99 + radius * math.sin(radians)

    donut_nodes = []
    angle = 0.0
    for _, color, percentage in language_mix:
        next_angle = angle + percentage * 3.6
        start_x, start_y = point(angle)
        end_x, end_y = point(next_angle)
        large_arc = 1 if next_angle - angle > 180 else 0
        donut_nodes.append(
            f'<path d="M {start_x:.2f} {start_y:.2f} A 48 48 0 {large_arc} 1 {end_x:.2f} {end_y:.2f}" '
            f'stroke="{color}" class="donut" />'
        )
        angle = next_angle

    legend_nodes = []
    for index, (name, color, percentage) in enumerate(language_mix):
        x = 28 + (index % 3) * 224
        y = 188 + (index // 3) * 20
        legend_nodes.append(
            f'<circle cx="{x + 4}" cy="{y - 4}" r="4" fill="{color}" />'
            f'<text x="{x + 15}" y="{y}" class="legend">'
            f'{html.escape(name)} {percentage:.1f}%</text>'
        )

    description = (
        f"{username}: {total} contributions over the rolling year, {active_days} active days, "
        f"a {current_streak}-day current streak, {public_repos} public repositories, and "
        f"{language_count} public-code languages."
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="720" height="228" viewBox="0 0 720 228" role="img" aria-labelledby="title desc">
  <title id="title">{html.escape(username)} GitHub overview</title>
  <desc id="desc">{html.escape(description)}</desc>
  <style>
    .card {{ fill: #f6f8fa; stroke: #d0d7de; }}
    .heading {{ fill: #1f2328; font: 650 18px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .subtle {{ fill: #656d76; font: 400 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .label {{ fill: #656d76; font: 600 10px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; text-transform: uppercase; letter-spacing: .7px; }}
    .legend {{ fill: #656d76; font: 500 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .metric {{ fill: #1f2328; font: 600 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .day {{ stroke: rgba(27, 31, 36, .06); }}
    .l0 {{ fill: #ebedf0; }} .l1 {{ fill: #9be9a8; }} .l2 {{ fill: #40c463; }} .l3 {{ fill: #30a14e; }} .l4 {{ fill: #216e39; }}
    .donut {{ fill: none; stroke-width: 15; }}
    .donut-track {{ fill: none; stroke: #eaeef2; stroke-width: 15; }}
    .donut-value {{ fill: #1f2328; font: 700 20px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    @media (prefers-color-scheme: dark) {{
      .card {{ fill: #0d1117; stroke: #30363d; }}
      .heading {{ fill: #f0f6fc; }}
      .subtle, .label, .legend {{ fill: #8b949e; }}
      .metric, .donut-value {{ fill: #f0f6fc; }}
      .day {{ stroke: rgba(240, 246, 252, .04); }}
      .l0 {{ fill: #161b22; }} .l1 {{ fill: #0e4429; }} .l2 {{ fill: #006d32; }} .l3 {{ fill: #26a641; }} .l4 {{ fill: #39d353; }}
      .donut-track {{ stroke: #21262d; }}
    }}
  </style>
  <rect x="1" y="1" width="718" height="226" rx="14" class="card" />
  <text x="28" y="31" class="heading">GitHub pulse</text>
  <text x="692" y="31" text-anchor="end" class="subtle">rolling 365 days · public repositories</text>
  <text x="28" y="55" class="label">CONTRIBUTION RHYTHM</text>
  {''.join(heatmap_nodes)}
  <text x="28" y="151" class="metric">{total:,} contributions  ·  {active_days} active days  ·  {current_streak}-day streak  ·  {public_repos} repos</text>
  <circle cx="600" cy="99" r="48" class="donut-track" />
  {''.join(donut_nodes)}
  <text x="600" y="96" text-anchor="middle" class="donut-value">{language_count}</text>
  <text x="600" y="112" text-anchor="middle" class="subtle">languages</text>
  <text x="28" y="172" class="label">PUBLIC-CODE MIX · LONGEST STREAK {longest_streak} DAYS</text>
  {''.join(legend_nodes)}
</svg>
'''


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} OUTPUT.svg", file=sys.stderr)
        return 2
    token = os.environ.get("GITHUB_TOKEN", "")
    username = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    if not token or not username:
        print("GITHUB_TOKEN and GITHUB_REPOSITORY_OWNER are required", file=sys.stderr)
        return 2

    today = dt.datetime.now(dt.timezone.utc).date()
    first_day = today - dt.timedelta(days=364)
    query = """
      query($login: String!, $from: DateTime!, $to: DateTime!) {
        user(login: $login) {
          contributionsCollection(from: $from, to: $to) {
            contributionCalendar {
              totalContributions
              weeks { contributionDays { date contributionCount } }
            }
          }
          repositories(
            first: 100
            privacy: PUBLIC
            isFork: false
            ownerAffiliations: OWNER
            orderBy: {field: UPDATED_AT, direction: DESC}
          ) {
            nodes {
              name
              isArchived
              languages(first: 100, orderBy: {field: SIZE, direction: DESC}) {
                edges { size node { name color } }
              }
            }
          }
        }
      }
    """
    data = graphql(
        token,
        query,
        {
            "login": username,
            "from": f"{first_day.isoformat()}T00:00:00Z",
            "to": f"{today.isoformat()}T23:59:59Z",
        },
    )["user"]
    calendar = data["contributionsCollection"]["contributionCalendar"]
    days = [item for week in calendar["weeks"] for item in week["contributionDays"]]
    by_date = {item["date"]: item["contributionCount"] for item in days}
    counts = [
        by_date.get((first_day + dt.timedelta(days=offset)).isoformat(), 0)
        for offset in range(365)
    ]
    current, longest = streaks(counts)

    repositories = [
        repo for repo in data["repositories"]["nodes"]
        if not repo["isArchived"] and repo["name"] != username
    ]
    language_sizes: dict[str, int] = {}
    language_colors: dict[str, str] = {}
    for repository in repositories:
        for edge in repository["languages"]["edges"]:
            name = edge["node"]["name"]
            if name == "Roff":
                continue
            language_sizes[name] = language_sizes.get(name, 0) + edge["size"]
            color = edge["node"].get("color") or "#8c959f"
            language_colors.setdefault(name, color)

    total_bytes = sum(language_sizes.values()) or 1
    ordered = sorted(language_sizes.items(), key=lambda item: item[1], reverse=True)
    top = ordered[:5]
    other_size = sum(size for _, size in ordered[5:])
    if other_size:
        top.append(("Other", other_size))
        language_colors["Other"] = "#8c959f"
    language_mix = [
        (name, language_colors[name], size * 100 / total_bytes)
        for name, size in top
    ]
    svg = render_svg(
        username=username,
        total=calendar["totalContributions"],
        active_days=sum(value > 0 for value in counts),
        current_streak=current,
        longest_streak=longest,
        public_repos=len(repositories),
        language_count=len(language_sizes),
        language_mix=language_mix,
        counts=counts,
        start_weekday=(first_day.weekday() + 1) % 7,
    )
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
