#!/usr/bin/env python3
"""Generate the SVG dashboard embedded in the GitHub profile README."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GRAPHQL_URL = "https://api.github.com/graphql"
DEFAULT_USER = "IvesLiu1026"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "profile-dashboard.svg"

QUERY = """
query ProfileDashboard($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            date
          }
        }
      }
    }
    repositories(
      first: 100
      ownerAffiliations: [OWNER]
      privacy: PUBLIC
      isFork: false
    ) {
      totalCount
      nodes {
        primaryLanguage {
          color
          name
        }
      }
    }
  }
}
"""


def github_data(token: str, login: str, today: dt.date) -> dict:
    payload = json.dumps(
        {
            "query": QUERY,
            "variables": {
                "login": login,
                "from": f"{today.year}-01-01T00:00:00Z",
                "to": f"{today.isoformat()}T23:59:59Z",
            },
        }
    ).encode()
    request = Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "IvesLiu1026-profile-dashboard",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except (HTTPError, URLError) as error:
        raise SystemExit(f"GitHub API request failed: {error}") from error

    if result.get("errors"):
        messages = "; ".join(error["message"] for error in result["errors"])
        raise SystemExit(f"GitHub GraphQL error: {messages}")
    user = result.get("data", {}).get("user")
    if user is None:
        raise SystemExit(f"GitHub user not found: {login}")
    return user


def current_streak(calendar: dict, today: dt.date) -> int:
    counts = {
        dt.date.fromisoformat(day["date"]): day["contributionCount"]
        for week in calendar["weeks"]
        for day in week["contributionDays"]
    }
    cursor = today
    if counts.get(cursor, 0) == 0:
        cursor -= dt.timedelta(days=1)

    streak = 0
    while counts.get(cursor, 0) > 0:
        streak += 1
        cursor -= dt.timedelta(days=1)
    return streak


def language_summary(repositories: list[dict]) -> list[tuple[str, str, int]]:
    counts: dict[tuple[str, str], int] = {}
    for repository in repositories:
        language = repository.get("primaryLanguage")
        if not language:
            continue
        key = (language["name"], language.get("color") or "#8c959f")
        counts[key] = counts.get(key, 0) + 1
    ranked = sorted(
        ((name, color, count) for (name, color), count in counts.items()),
        key=lambda item: (-item[2], item[0].lower()),
    )
    return ranked


def render_svg(login: str, user: dict, year: int, today: dt.date) -> str:
    calendar = user["contributionsCollection"]["contributionCalendar"]
    repository_data = user["repositories"]
    repositories = repository_data["nodes"]
    languages = language_summary(repositories)
    displayed_languages = languages[:5]
    total_displayed_languages = sum(item[2] for item in displayed_languages) or 1
    streak = current_streak(calendar, today)
    stats = [
        (f"{year} CONTRIBUTIONS", calendar["totalContributions"]),
        ("CURRENT STREAK", f"{streak} {'day' if streak == 1 else 'days'}"),
        ("PUBLIC PROJECTS", repository_data["totalCount"]),
        ("PUBLIC LANGUAGES", len(languages)),
    ]

    cards = []
    for index, (label, value) in enumerate(stats):
        x = 32 + index * 230
        cards.append(
            f'''<g transform="translate({x} 80)">
  <rect class="card" width="210" height="92" rx="12"/>
  <text class="metric" x="18" y="48">{html.escape(str(value))}</text>
  <text class="label" x="18" y="72">{html.escape(label)}</text>
</g>'''
        )

    bar_x, bar_y, bar_width = 32, 216, 916
    segments = []
    legends = []
    used_width = 0.0
    for index, (name, color, count) in enumerate(displayed_languages):
        width = bar_width * count / total_displayed_languages
        segments.append(
            f'<rect x="{bar_x + used_width:.1f}" y="{bar_y}" width="{width:.1f}" '
            f'height="10" fill="{html.escape(color)}"/>'
        )
        used_width += width
        legend_x = 32 + index * 180
        legends.append(
            f'<circle cx="{legend_x + 5}" cy="258" r="5" fill="{html.escape(color)}"/>'
            f'<text class="legend" x="{legend_x + 17}" y="263">'
            f'{html.escape(name)} · {count}</text>'
        )

    safe_login = html.escape(login)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="980" height="318" viewBox="0 0 980 318" role="img" aria-labelledby="title desc">
  <title id="title">{safe_login} engineering dashboard</title>
  <desc id="desc">GitHub contribution, streak, project, star, and language summary.</desc>
  <style>
    .background {{ fill: #ffffff; stroke: #d0d7de; }}
    .card {{ fill: #f6f8fa; stroke: #d8dee4; }}
    .heading, .metric {{ fill: #1f2328; }}
    .label, .legend, .note {{ fill: #636c76; }}
    .heading {{ font: 700 17px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; letter-spacing: .08em; }}
    .metric {{ font: 700 30px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .label {{ font: 600 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; letter-spacing: .06em; }}
    .legend {{ font: 500 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .note {{ font: 400 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    @media (prefers-color-scheme: dark) {{
      .background {{ fill: #0d1117; stroke: #30363d; }}
      .card {{ fill: #161b22; stroke: #30363d; }}
      .heading, .metric {{ fill: #f0f6fc; }}
      .label, .legend, .note {{ fill: #8b949e; }}
    }}
  </style>
  <rect class="background" x="1" y="1" width="978" height="316" rx="16"/>
  <text class="heading" x="32" y="48">ENGINEERING DASHBOARD</text>
  <circle cx="930" cy="43" r="5" fill="#3fb950"/>
  <text class="label" x="914" y="62" text-anchor="middle">LIVE</text>
  {''.join(cards)}
  <text class="label" x="32" y="202">TOP LANGUAGES ACROSS PUBLIC PROJECTS</text>
  <clipPath id="language-bar"><rect x="32" y="216" width="916" height="10" rx="5"/></clipPath>
  <g clip-path="url(#language-bar)">{''.join(segments)}</g>
  {''.join(legends)}
  <text class="note" x="32" y="296">Contribution totals include anonymized private activity; project and language totals use public, non-fork repositories only.</text>
</svg>
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default=os.environ.get("GITHUB_USER", DEFAULT_USER))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("Set GITHUB_TOKEN or GH_TOKEN before running this script.")

    today = dt.datetime.now(dt.timezone.utc).date()
    user = github_data(token, args.user, today)
    svg = render_svg(args.user, user, today.year, today)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")
    print(f"Updated {args.output}")


if __name__ == "__main__":
    main()
