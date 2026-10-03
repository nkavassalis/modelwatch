"""RSS 2.0 generation."""

from __future__ import annotations

import email.utils
import time
from xml.sax.saxutils import escape

from .config import FeedMeta


def _rfc822(epoch: float) -> str:
    return email.utils.formatdate(epoch, usegmt=True)


def render_feed(meta: FeedMeta, entries: list[dict], link: str) -> str:
    """entries: dicts with model_id, category, url, first_seen."""
    now = _rfc822(time.time())
    items = []
    for e in entries:
        cat = f"<category>{escape(e['category'])}</category>" if e.get("category") else ""
        title = escape(e["model_id"])
        items.append(
            "    <item>\n"
            f"      <title>{title}</title>\n"
            f"      <link>{escape(e['url'])}</link>\n"
            f"      <guid isPermaLink=\"false\">{title}</guid>\n"
            f"      {cat}\n"
            f"      <pubDate>{_rfc822(e['first_seen'])}</pubDate>\n"
            f"      <description>Newly trending: {title}"
            + (f" ({escape(e['category'])})" if e.get("category") else "")
            + "</description>\n"
            "    </item>"
        )
    items_xml = "\n".join(items)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<rss version=\"2.0\">\n"
        "  <channel>\n"
        f"    <title>{escape(meta.title)}</title>\n"
        f"    <link>{escape(meta.site_url)}</link>\n"
        f"    <description>{escape(meta.description)}</description>\n"
        f"    <lastBuildDate>{now}</lastBuildDate>\n"
        f"{items_xml}\n"
        "  </channel>\n"
        "</rss>\n"
    )
