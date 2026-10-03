"""Persistent state: seen models, cached entries, fetch timestamps.

The state file is a single JSON document:

    {
      "last_fetch": 1730000000.0,          # epoch seconds of last successful fetch
      "seen": ["Qwen/Qwen-Image-2.1", ...], # every model ever seen in top N
      "entries": [                          # feed items, newest first
        {"model_id": "...", "category": "...", "url": "...", "first_seen": 173...}
      ]
    }
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .fetcher import TrendingModel

MAX_ENTRIES = 300  # cap on feed history kept in the state file


class State:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict[str, Any] = {
            "last_fetch": 0.0,
            "seen": [],
            "entries": [],
        }
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
            self.data.setdefault("last_fetch", 0.0)
            self.data.setdefault("seen", [])
            self.data.setdefault("entries", [])

    # -- cache TTL -------------------------------------------------------
    @property
    def last_fetch(self) -> float:
        return float(self.data.get("last_fetch") or 0.0)

    def cache_expired(self, ttl_hours: float, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        return (now - self.last_fetch) >= ttl_hours * 3600.0

    def mark_fetched(self, now: float | None = None) -> None:
        self.data["last_fetch"] = now if now is not None else time.time()

    # -- seen set / entries ----------------------------------------------
    @property
    def seen(self) -> set[str]:
        return set(self.data["seen"])

    def record(self, models: list[TrendingModel], now: float | None = None) -> int:
        """Record a fresh ranking; returns number of *new* models added."""
        now = now if now is not None else time.time()
        seen = self.seen
        new_count = 0
        for m in models:
            if m.model_id in seen:
                continue
            seen.add(m.model_id)
            self.data["entries"].insert(0, {
                "model_id": m.model_id,
                "category": m.category,
                "url": m.url,
                "first_seen": now,
            })
            new_count += 1
        self.data["seen"] = sorted(seen)
        self.data["entries"] = self.data["entries"][:MAX_ENTRIES]
        return new_count

    @property
    def entries(self) -> list[dict[str, Any]]:
        return self.data["entries"]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1))
        tmp.replace(self.path)
