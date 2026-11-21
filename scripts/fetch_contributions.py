"""Fetch the last year of contributions from GitHub.

Writes data/contributions.json:
    {"updated": ..., "totalContributions": n,
     "days": [{"date": "YYYY-MM-DD", "count": n}, ...]}

Primary source: GitHub GraphQL API (GH_TOKEN / GITHUB_TOKEN). Fallback with
no token: scrape the calendar embedded in the public profile page.
Flattens the weeks grid into one sorted list of days.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "contributions.json"

QUERY = """\
query($login:String!) {
  user(login:$login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}"""


def fetch(login: str, token: str) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(  # noqa: S310 - fixed api.github.com
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-cards",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        payload = json.load(resp)
    if payload.get("errors"):
        raise SystemExit(f"GraphQL errors: {payload['errors']}")
    cal = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = []
    for week in cal["weeks"]:
        for d in week["contributionDays"]:
            days.append({"date": d["date"][:10], "count": d["contributionCount"]})
    days.sort(key=lambda d: d["date"])
    return {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "totalContributions": cal["totalContributions"],
        "days": days,
    }


def fetch_scrape(login: str) -> dict:
    """Fallback without auth: the /users/<login>/contributions fragment."""
    req = urllib.request.Request(  # noqa: S310 - fixed github.com
        f"https://github.com/users/{login}/contributions",
        headers={"User-Agent": "Mozilla/5.0 profile-cards"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        html = resp.read().decode("utf-8", "replace")

    # day components carry the date; the sr-only tool-tips carry the count
    comps = []
    for tag in re.findall(r"<[^>]+>", html):
        if "contribution-day-component" not in tag or "data-date" not in tag:
            continue
        cid = re.search(r'id="(contribution-day-component-\d+-\d+)"', tag)
        date = re.search(r'data-date="(\d{4}-\d{2}-\d{2})"', tag)
        if cid and date:
            comps.append((cid.group(1), date.group(1)))
    if not comps:
        raise SystemExit("could not find contribution day components")
    tips = dict(re.findall(
        r'<tool-tip[^>]*\bfor="(contribution-day-component-\d+-\d+)"[^>]*>([^<]*)<', html))

    def count_of(text: str) -> int:
        text = text.strip()
        if text.startswith("No contributions"):
            return 0
        m = re.match(r"([\d,]+) contributions? on", text)
        return int(m.group(1).replace(",", "")) if m else 0

    days = [{"date": date, "count": count_of(tips.get(cid, ""))} for cid, date in comps]
    days.sort(key=lambda d: d["date"])
    return {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "totalContributions": sum(d["count"] for d in days),
        "days": days,
    }


def main() -> int:
    login = os.environ.get("GH_USER", "eduardomendozavillar")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        try:
            data = fetch(login, token)
        except SystemExit:
            raise
        except Exception as exc:  # fall back to scraping on any API trouble
            print(f"GraphQL failed ({exc}); falling back to profile page", file=sys.stderr)
            data = fetch_scrape(login)
    else:
        data = fetch_scrape(login)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"wrote {OUT} ({data['totalContributions']} contributions, {len(data['days'])} days)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
