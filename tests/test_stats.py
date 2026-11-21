"""Tests for the contribution stats derived from data/contributions.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from stats import active_days, current_streak, longest_streak, monthly_totals, most_active_day  # noqa: E402


def D(date: str, count: int) -> dict:
    return {"date": date, "count": count}


# Synthetic calendar: Jan 2026 has 3 active days, streaks on the first days,
# and a peak on 2026-01-14.
CAL = [
    D("2026-01-01", 3),
    D("2026-01-02", 5),
    D("2026-01-03", 0),
    D("2026-01-04", 1),
    D("2026-01-05", 2),
    D("2026-01-06", 0),
    D("2026-01-07", 0),
    D("2026-01-14", 9),
    D("2026-01-31", 4),
    D("2026-02-01", 1),
    D("2026-02-02", 0),
    D("2026-02-15", 6),
]


class TestActiveDays:
    def test_counts_days_with_contributions(self):
        assert active_days(CAL) == 8

    def test_empty_calendar(self):
        assert active_days([]) == 0


class TestCurrentStreak:
    def test_counts_back_from_last_day(self):
        # last day (02-15) active, day before (02-02) inactive -> streak 1
        assert current_streak(CAL) == 1

    def test_inactive_today_counts_yesterday(self):
        cal = CAL + [D("2026-02-15", 0), D("2026-02-16", 2)]
        assert current_streak(cal) == 1

    def test_no_streak(self):
        cal = [D("2026-02-15", 0)]
        assert current_streak(cal) == 0

    def test_long_run(self):
        cal = [D(f"2026-03-{d:02d}", 1) for d in range(1, 6)]
        assert current_streak(cal) == 5


class TestLongestStreak:
    def test_finds_longest_run(self):
        start, end, length = longest_streak(CAL)
        assert (start, end, length) == ("2026-01-01", "2026-01-02", 2)

    def test_tie_keeps_first(self):
        start, end, length = longest_streak(CAL + [D("2026-02-28", 3), D("2026-03-01", 3)])
        assert (start, end, length) == ("2026-01-01", "2026-01-02", 2)


class TestMonthlyTotals:
    def test_groups_by_month_in_order(self):
        months = monthly_totals(CAL)
        assert [m["ym"] for m in months] == ["2026-01", "2026-02"]
        assert months[0]["total"] == 24
        assert months[1]["total"] == 7

    def test_labels(self):
        months = monthly_totals(CAL)
        assert months[0]["label"] == "Jan 2026"

    def test_empty(self):
        assert monthly_totals([]) == []


class TestMostActiveDay:
    def test_peak(self):
        assert most_active_day(CAL) == {"date": "2026-01-14", "count": 9}

    def test_all_zero(self):
        assert most_active_day([D("2026-01-01", 0)]) is None


class TestSampleFile:
    """The committed sample data must be a valid, self-consistent dataset."""

    def test_sample_parses_and_has_a_year_of_days(self):
        data = json.loads((Path(__file__).resolve().parent.parent / "data" / "contributions.json").read_text(encoding="utf-8"))
        days = data["days"]
        assert len(days) >= 360
        assert all(set(d) >= {"date", "count"} for d in days)
        assert days == sorted(days, key=lambda d: d["date"])
        assert sum(d["count"] for d in days) == data["totalContributions"]
        # stats functions run on it without raising
        assert current_streak(days) >= 0
        assert monthly_totals(days)
