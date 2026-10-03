"""Core refresh logic shared by serve and publish modes."""

from __future__ import annotations

import logging
import threading

from .config import Config, website_to_api_url
from .feed import render_feed
from .fetcher import fetch_trending
from .state import State

log = logging.getLogger("modelwatch")


class Refresher:
    """Refreshes state + cached feed XML, honouring the cache TTL."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.state = State(cfg.state_file)
        self.feed_xml: str = self._render()
        self._lock = threading.Lock()

    def _render(self) -> str:
        return render_feed(
            self.cfg.feed, self.state.entries, link=self.cfg.feed.site_url
        )

    def refresh_if_stale(self, force: bool = False) -> bool:
        """Fetch + record + re-render unless cache is fresh. Returns True if fetched."""
        with self._lock:
            if not force and not self.state.cache_expired(self.cfg.cache_ttl_hours):
                return False
            api_url = website_to_api_url(self.cfg.source_url, self.cfg.top_n)
            log.info("fetching %s", api_url)
            models = fetch_trending(api_url)
            # Only consider the top_n slice (API may return more).
            models = models[: self.cfg.top_n]
            new = self.state.record(models)
            self.state.mark_fetched()
            self.state.save()
            self.feed_xml = self._render()
            log.info("fetched %d models, %d new", len(models), new)
            return True

    def save_feed_file(self) -> None:
        self.cfg.feed_file.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.feed_file.write_text(self.feed_xml)
