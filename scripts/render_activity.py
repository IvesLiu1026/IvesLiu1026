#!/usr/bin/env python3
"""Render a privacy-safe rolling GitHub activity card as a static SVG."""

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


def weekly_totals(days: list[dict], first_day: dt.date) -> list[int]:
    totals = [0] * 53
    for item in days:
        day = dt.date.fromisoformat(item["date"])
        offset = (day - first_day).days
        if 0 <= offset < 365:
            totals[min(offset // 7, 52)] += item["contributionCount"]
    while len(totals) > 52:
        totals.pop(0)
    return totals


def render_svg(
    *,
    username: str,
    total: int,
    active_days: int,
    current_streak: int,
    longest_streak: int,
    public_repos: int,
    languages: int,
    weeks: list[int],
) -> str:
    maximum = max(weeks, default=1) or 1
    bars = []
    for index, value in enumerate(weeks):
        height = 3 if value == 0 else 4 + round(24 * value / maximum)
        opacity = 0.20 if value == 0 else 0.45 + 0.55 * value / maximum
        bars.append(
            f'<rect x="{68 + index * 12}" y="{218 - height}" width="8" '
            f'height="{height}" rx="2" class="pulse" opacity="{opacity:.2f}" />'
        )

    metrics = [
        (f"{total:,}", "contributions"),
        (str(active_days), "active days"),
        (str(current_streak), "current streak"),
        (str(longest_streak), "longest streak"),
    ]
    tiles = []
    for index, (value, label) in enumerate(metrics):
        x = 28 + index * 181
        tiles.append(
            f'<g transform="translate({x},78)">'
            '<rect width="165" height="82" rx="12" class="tile" />'
            f'<text x="16" y="38" class="value">{html.escape(value)}</text>'
            f'<text x="16" y="62" class="label">{html.escape(label)}</text>'
            '</g>'
        )

    description = (
        f"{username}: {total} contributions over the rolling year, {active_days} active days, "
        f"a {current_streak}-day current streak, and a {longest_streak}-day longest streak."
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="760" height="258" viewBox="0 0 760 258" role="img" aria-labelledby="title desc">
  <title id="title">{html.escape(username)} GitHub activity snapshot</title>
  <desc id="desc">{html.escape(description)}</desc>
  <style>
    .card {{ fill: #f6f8fa; stroke: #d0d7de; }}
    .tile {{ fill: #ffffff; stroke: #d8dee4; }}
    .heading {{ fill: #1f2328; font: 600 20px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .subtle {{ fill: #656d76; font: 400 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .value {{ fill: #1f883d; font: 700 27px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .label {{ fill: #656d76; font: 500 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; text-transform: uppercase; letter-spacing: .7px; }}
    .pulse {{ fill: #2da44e; }}
    @media (prefers-color-scheme: dark) {{
      .card {{ fill: #0d1117; stroke: #30363d; }}
      .tile {{ fill: #161b22; stroke: #30363d; }}
      .heading {{ fill: #f0f6fc; }}
      .subtle, .label {{ fill: #8b949e; }}
      .value {{ fill: #3fb950; }}
      .pulse {{ fill: #3fb950; }}
    }}
  </style>
  <rect x="1" y="1" width="758" height="256" rx="16" class="card" />
  <text x="28" y="37" class="heading">365-day activity snapshot</text>
  <text x="28" y="57" class="subtle">Public profile activity · rolling daily window · generated on GitHub Actions</text>
  {''.join(tiles)}
  <text x="28" y="190" class="subtle">ACTIVITY PULSE</text>
  {''.join(bars)}
  <text x="732" y="238" text-anchor="end" class="subtle">{public_repos} public repos · {languages} primary languages</text>
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
            nodes { name isArchived primaryLanguage { name } }
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
    language_names = {
        repo["primaryLanguage"]["name"]
        for repo in repositories
        if repo.get("primaryLanguage")
    }
    svg = render_svg(
        username=username,
        total=calendar["totalContributions"],
        active_days=sum(value > 0 for value in counts),
        current_streak=current,
        longest_streak=longest,
        public_repos=len(repositories),
        languages=len(language_names),
        weeks=weekly_totals(days, first_day),
    )
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
