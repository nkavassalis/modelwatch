"""RSS 2.0 generation."""

from __future__ import annotations

import email.utils
import time
from xml.sax.saxutils import escape

from .config import FeedMeta


def _rfc822(epoch: float) -> str:
    return email.utils.formatdate(epoch, usegmt=True)


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _ymd(epoch: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(epoch))


def render_feed(meta: FeedMeta, entries: list[dict], link: str) -> str:
    """entries: dicts with model_id, category, url, first_seen, created (optional)."""
    now = _rfc822(time.time())
    items = []
    for e in entries:
        cat = f"<category>{escape(e['category'])}</category>" if e.get("category") else ""
        title = escape(e["model_id"])
        created = float(e.get("created") or 0.0)
        created_el = (
            f"\n      <dcterms:created>{_iso(created)}</dcterms:created>"
            if created else ""
        )
        desc = f"Newly trending: {title}" + (
            f" ({escape(e['category'])})" if e.get("category") else ""
        )
        if created:
            desc += f" Uploaded to Hugging Face {_ymd(created)}."
        items.append(
            "    <item>\n"
            f"      <title>{title}</title>\n"
            f"      <link>{escape(e['url'])}</link>\n"
            f"      <guid isPermaLink=\"false\">{title}</guid>\n"
            f"      {cat}{created_el}\n"
            f"      <pubDate>{_rfc822(e['first_seen'])}</pubDate>\n"
            f"      <description>{desc}</description>\n"
            "    </item>"
        )
    items_xml = "\n".join(items)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<rss version=\"2.0\" xmlns:dcterms=\"http://purl.org/dc/terms/\">\n"
        "  <channel>\n"
        f"    <title>{escape(meta.title)}</title>\n"
        f"    <link>{escape(meta.site_url)}</link>\n"
        f"    <description>{escape(meta.description)}</description>\n"
        f"    <lastBuildDate>{now}</lastBuildDate>\n"
        f"{items_xml}\n"
        "  </channel>\n"
        "</rss>\n"
    )
