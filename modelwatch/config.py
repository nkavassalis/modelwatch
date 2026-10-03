"""Configuration loading for modelwatch.

Config is a small YAML file. See config.example.yml.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any

import yaml

DEFAULT_SOURCE_URL = "https://huggingface.co/models?sort=trending"
DEFAULT_TOP_N = 100
DEFAULT_CACHE_TTL_HOURS = 24.0
DEFAULT_STATE_DIR = "./.modelwatch"


@dataclasses.dataclass
class S3Config:
    bucket: str = ""
    key: str = "feed.xml"
    region: str = "us-east-1"
    distribution_id: str = ""  # optional; invalidation issued after upload if set


@dataclasses.dataclass
class FeedMeta:
    title: str = "Newly Trending Hugging Face Models"
    description: str = (
        "Models that newly entered the Hugging Face trending leaderboard."
    )
    site_url: str = "https://huggingface.co/models?sort=trending"


@dataclasses.dataclass
class Config:
    source_url: str = DEFAULT_SOURCE_URL
    top_n: int = DEFAULT_TOP_N
    cache_ttl_hours: float = DEFAULT_CACHE_TTL_HOURS
    state_dir: str = DEFAULT_STATE_DIR
    feed: FeedMeta = dataclasses.field(default_factory=FeedMeta)
    s3: S3Config = dataclasses.field(default_factory=S3Config)

    @property
    def state_file(self) -> Path:
        return Path(self.state_dir) / "state.json"

    @property
    def feed_file(self) -> Path:
        return Path(self.state_dir) / "feed.xml"


def website_to_api_url(url: str, top_n: int) -> str:
    """Translate a huggingface.co/models browse URL into the JSON API URL.

    Anything that is already an /api/ URL is passed through, with the
    limit parameter normalised to top_n.
    """
    if "huggingface.co/models" in url and "/api/" not in url:
        return (
            "https://huggingface.co/api/models"
            f"?sort=trendingScore&direction=-1&limit={top_n}"
        )
    # Normalise limit on API urls so top_n always wins.
    url = re.sub(r"([?&])limit=\d+", rf"\g<1>limit={top_n}", url)
    if "limit=" not in url:
        url = f"{url}&limit={top_n}" if "?" in url else f"{url}?limit={top_n}"
    return url


def load_config(path: str | Path) -> Config:
    raw: dict[str, Any] = {}
    p = Path(path)
    if p.exists():
        raw = yaml.safe_load(p.read_text()) or {}

    feed_raw = raw.get("feed") or {}
    s3_raw = raw.get("s3") or {}

    cfg = Config(
        source_url=str(raw.get("source_url", DEFAULT_SOURCE_URL)),
        top_n=int(raw.get("top_n", DEFAULT_TOP_N)),
        cache_ttl_hours=float(raw.get("cache_ttl_hours", DEFAULT_CACHE_TTL_HOURS)),
        state_dir=str(raw.get("state_dir", DEFAULT_STATE_DIR)),
        feed=FeedMeta(
            title=str(feed_raw.get("title", FeedMeta.title)),
            description=str(feed_raw.get("description", FeedMeta.description)),
            site_url=str(feed_raw.get("site_url", FeedMeta.site_url)),
        ),
        s3=S3Config(
            bucket=str(s3_raw.get("bucket", "")),
            key=str(s3_raw.get("key", "feed.xml")),
            region=str(s3_raw.get("region", "us-east-1")),
            distribution_id=str(s3_raw.get("distribution_id", "")),
        ),
    )
    return cfg
