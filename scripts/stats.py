"""Contribution statistics derived from a flat calendar of days.

`days` is a list of {"date": "YYYY-MM-DD", "count": int} sorted ascending,
as written by fetch_contributions.py.
"""
from __future__ import annotations

from datetime import date, timedelta

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _parse(day: dict) -> date:
    y, m, d = (int(p) for p in day["date"].split("-"))
    return date(y, m, d)


def active_days(days: list[dict]) -> int:
    """Days with at least one contribution."""
    return sum(1 for d in days if d["count"] > 0)


def monthly_totals(days: list[dict]) -> list[dict]:
    """Contribution totals grouped by month, in calendar order."""
    out: dict[str, int] = {}
    for d in days:
        total = out.setdefault(d["date"][:7], 0)
        out[d["date"][:7]] = total + d["count"]
    months = []
    for ym, total in out.items():
        y, m = ym.split("-")
        months.append({"ym": ym, "label": f"{MONTH_ABBR[int(m) - 1]} {y}", "total": total})
    return months


def current_streak(days: list[dict], today: date | None = None) -> int:
    """Consecutive active days ending today; today counts if active, else yesterday."""
    if not days:
        return 0
    today = today or _parse(days[-1])
    by_date = {_parse(d): d["count"] for d in days}
    streak = 0
    cursor = today
    # today with zero contributions does not break the streak: start at yesterday
    if by_date.get(cursor, 0) == 0:
        cursor -= timedelta(days=1)
    while by_date.get(cursor, 0) > 0:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def longest_streak(days: list[dict]) -> tuple[str, str, int] | None:
    """Longest run of consecutive active days as (start, end, length); ties keep the first."""
    best: tuple[str, str, int] | None = None
    run_start: date | None = None
    prev: date | None = None
    for d in days:
        cur = _parse(d)
        consecutive = prev is not None and (cur - prev).days == 1
        if d["count"] > 0:
            if not consecutive or run_start is None:
                run_start = cur
            prev = cur
            length = (cur - run_start).days + 1
            if best is None or length > best[2]:
                best = (run_start.isoformat(), cur.isoformat(), length)
        else:
            run_start = None
            prev = None
    return best


def most_active_day(days: list[dict]) -> dict | None:
    """The single day with the most contributions."""
    if not days or all(d["count"] == 0 for d in days):
        return None
    top = max(days, key=lambda d: d["count"])
    return {"date": top["date"], "count": top["count"]}
