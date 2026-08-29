"""
HistoryStore — Persistent daily posture statistics.

Mirrors macOS HistoryStore.swift:
- DayStat data class with good/bad seconds, slouch count, session count
- JSON file persistence
- 7-day history retrieval with zero-filled gaps
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional


DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "history.json")


@dataclass
class DayStat:
    day: str                  # "YYYY-MM-DD"
    good_seconds: float = 0.0
    bad_seconds: float = 0.0
    slouches: int = 0
    sessions: int = 0

    @property
    def total_seconds(self) -> float:
        return self.good_seconds + self.bad_seconds

    @property
    def good_minutes(self) -> float:
        return self.good_seconds / 60.0

    @property
    def bad_minutes(self) -> float:
        return self.bad_seconds / 60.0

    @property
    def good_percent(self) -> float:
        total = self.total_seconds
        if total <= 0:
            return 0.0
        return (self.good_seconds / total) * 100.0

    @property
    def short_weekday(self) -> str:
        try:
            dt = datetime.strptime(self.day, "%Y-%m-%d")
            return dt.strftime("%a")  # e.g. "Mon"
        except ValueError:
            return self.day


class HistoryStore:
    def __init__(self, data_file: str = DATA_FILE):
        self._data_file = data_file
        self._days: dict[str, DayStat] = {}
        self._load()

    def _load(self):
        """Load history from JSON file."""
        try:
            if os.path.exists(self._data_file):
                with open(self._data_file, "r") as f:
                    raw = json.load(f)
                for key, val in raw.items():
                    self._days[key] = DayStat(
                        day=val.get("day", key),
                        good_seconds=val.get("good_seconds", 0.0),
                        bad_seconds=val.get("bad_seconds", 0.0),
                        slouches=val.get("slouches", 0),
                        sessions=val.get("sessions", 0),
                    )
        except Exception as e:
            print(f"History load error: {e}")
            self._days = {}

    def _save(self):
        """Persist history to JSON file."""
        try:
            raw = {key: asdict(stat) for key, stat in self._days.items()}
            with open(self._data_file, "w") as f:
                json.dump(raw, f, indent=2)
        except Exception as e:
            print(f"History save error: {e}")

    def record(self, good: float, bad: float, slouches: int, date: Optional[datetime] = None):
        """Accumulate stats into the current date's entry and save."""
        if date is None:
            date = datetime.now()
        key = date.strftime("%Y-%m-%d")

        if key not in self._days:
            self._days[key] = DayStat(day=key, sessions=0)

        stat = self._days[key]
        stat.good_seconds += good
        stat.bad_seconds += bad
        stat.slouches += slouches
        stat.sessions += 1
        self._save()

    def last_days(self, count: int = 7, now: Optional[datetime] = None) -> list[DayStat]:
        """Return ordered list of DayStat for the past N calendar days, filling gaps with zeros."""
        if now is None:
            now = datetime.now()
        result = []
        for i in range(count - 1, -1, -1):
            d = now - timedelta(days=i)
            key = d.strftime("%Y-%m-%d")
            if key in self._days:
                result.append(self._days[key])
            else:
                result.append(DayStat(day=key))
        return result

    def clear(self):
        """Wipe all history."""
        self._days = {}
        self._save()
