#!/usr/bin/env python3
"""Render a compact, privacy-safe GitHub profile overview as static SVG."""

from __future__ import annotations

import datetime as dt
import html
import json
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
) -> str:
    metrics = [
        (f"{total:,}", "contributions"),
        (str(active_days), "active days"),
        (f"{current_streak} days", "current streak"),
        (str(public_repos), "public repos"),
    ]
    metric_nodes = []
    for index, (value, label) in enumerate(metrics):
        x = 28 + index * 177
        metric_nodes.append(
            f'<g transform="translate({x},63)">'
            f'<text x="0" y="24" class="value">{html.escape(value)}</text>'
            f'<text x="0" y="45" class="label">{html.escape(label)}</text>'
            '</g>'
        )

    bar_nodes = []
    cursor = 28.0
    for _, color, percentage in language_mix:
        width = 664 * percentage / 100
        bar_nodes.append(
            f'<rect x="{cursor:.2f}" y="137" width="{width:.2f}" height="10" fill="{color}" />'
        )
        cursor += width

    legend_nodes = []
    for index, (name, color, percentage) in enumerate(language_mix):
        x = 28 + (index % 3) * 224
        y = 173 + (index // 3) * 21
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
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="720" height="212" viewBox="0 0 720 212" role="img" aria-labelledby="title desc">
  <title id="title">{html.escape(username)} GitHub overview</title>
  <desc id="desc">{html.escape(description)}</desc>
  <style>
    .card {{ fill: #f6f8fa; stroke: #d0d7de; }}
    .heading {{ fill: #1f2328; font: 600 18px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .subtle {{ fill: #656d76; font: 400 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .value {{ fill: #1f883d; font: 700 22px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .label {{ fill: #656d76; font: 500 10px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; text-transform: uppercase; letter-spacing: .6px; }}
    .legend {{ fill: #656d76; font: 500 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .divider {{ stroke: #d8dee4; }}
    @media (prefers-color-scheme: dark) {{
      .card {{ fill: #0d1117; stroke: #30363d; }}
      .heading {{ fill: #f0f6fc; }}
      .subtle, .label, .legend {{ fill: #8b949e; }}
      .value {{ fill: #3fb950; }}
      .divider {{ stroke: #30363d; }}
    }}
  </style>
  <rect x="1" y="1" width="718" height="210" rx="14" class="card" />
  <text x="28" y="31" class="heading">GitHub at a glance</text>
  <text x="692" y="31" text-anchor="end" class="subtle">rolling 365 days · public-code mix</text>
  {''.join(metric_nodes)}
  <path d="M189 62v46 M366 62v46 M543 62v46" class="divider" />
  <text x="28" y="128" class="label">LANGUAGE DISTRIBUTION · {language_count} LANGUAGES · LONGEST STREAK {longest_streak} DAYS</text>
  <clipPath id="bar"><rect x="28" y="137" width="664" height="10" rx="5" /></clipPath>
  <g clip-path="url(#bar)">{''.join(bar_nodes)}</g>
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
    )
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
