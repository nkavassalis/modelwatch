"""Tests for modelwatch. All network access is mocked."""

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from modelwatch.config import Config, FeedMeta, load_config, website_to_api_url
from modelwatch.core import Refresher
from modelwatch.feed import render_feed
from modelwatch.fetcher import TrendingModel, _humanize, fetch_trending
from modelwatch.state import State


# ---- config -------------------------------------------------------------

def test_defaults():
    cfg = Config()
    assert cfg.top_n == 100
    assert cfg.cache_ttl_hours == 24
    assert cfg.source_url == "https://huggingface.co/models?sort=trending"


def test_website_url_translated_to_api():
    url = website_to_api_url("https://huggingface.co/models?sort=trending", 50)
    assert url == "https://huggingface.co/api/models?sort=trendingScore&direction=-1&limit=50"


def test_api_url_limit_normalised():
    url = website_to_api_url("https://huggingface.co/api/models?sort=trendingScore&limit=5", 100)
    assert "limit=100" in url and "limit=5&" not in url


def test_load_config_yaml(tmp_path):
    p = tmp_path / "config.yml"
    p.write_text("top_n: 25\ncache_ttl_hours: 1\ns3:\n  bucket: b\n")
    cfg = load_config(p)
    assert cfg.top_n == 25 and cfg.cache_ttl_hours == 1.0 and cfg.s3.bucket == "b"


def test_load_config_missing_file_gives_defaults(tmp_path):
    cfg = load_config(tmp_path / "nope.yml")
    assert cfg.top_n == 100


# ---- fetcher --------------------------------------------------------------

class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_trending_parses_and_labels(monkeypatch):
    models_payload = [
        {"id": "Qwen/Qwen-Image-2.1", "pipeline_tag": "text-to-image"},
        {"id": "meta/Llama-5", "pipeline_tag": None},
        {"id": "no/tag"},
    ]
    tags_payload = {"pipeline_tag": [
        {"id": "text-to-image", "label": "Text-to-Image"},
    ]}

    def fake_get(url, **kw):
        if "models-tags-by-type" in url:
            return FakeResp(tags_payload)
        return FakeResp(models_payload)

    monkeypatch.setattr("modelwatch.fetcher.requests.get", fake_get)
    got = fetch_trending("https://huggingface.co/api/models?sort=trendingScore")
    assert got[0] == TrendingModel("Qwen/Qwen-Image-2.1", "Text-to-Image")
    assert got[1].category == ""  # unknown tag with no label -> no fallback noise
    assert got[0].url == "https://huggingface.co/Qwen/Qwen-Image-2.1"


def test_humanize_fallback():
    assert _humanize("text-to-image") == "Text-to-Image"
    assert _humanize("automatic-speech-recognition") == "Automatic Speech Recognition"


# ---- state ----------------------------------------------------------------

def test_state_first_seen_only_once(tmp_path):
    st = State(tmp_path / "state.json")
    m1 = TrendingModel("A/A", "Text Generation")
    m2 = TrendingModel("B/B", "")
    assert st.record([m1, m2]) == 2
    # B dips out, comes back: no re-add
    assert st.record([m1]) == 0
    assert st.record([m1, m2]) == 0
    assert len(st.entries) == 2


def test_state_persistence_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    st = State(p)
    st.record([TrendingModel("X/X", "X")], now=1000)
    st.mark_fetched(now=1000)
    st.save()
    st2 = State(p)
    assert st2.seen == {"X/X"}
    assert st2.last_fetch == 1000
    assert st2.entries[0]["model_id"] == "X/X"


def test_cache_ttl(tmp_path):
    st = State(tmp_path / "state.json")
    assert st.cache_expired(24)  # never fetched
    st.mark_fetched(now=0)
    assert not st.cache_expired(24, now=12 * 3600)
    assert st.cache_expired(24, now=24 * 3600 + 1)


# ---- feed -----------------------------------------------------------------

def test_render_feed_structure():
    entries = [
        {"model_id": "Qwen/Qwen-Image-2.1", "category": "Text-to-Image",
         "url": "https://huggingface.co/Qwen/Qwen-Image-2.1", "first_seen": 1700000000},
    ]
    xml = render_feed(FeedMeta(), entries, link="https://example.com")
    root = ET.fromstring(xml)
    item = root.find("./channel/item")
    assert item.find("title").text == "Qwen/Qwen-Image-2.1"
    assert item.find("category").text == "Text-to-Image"
    assert item.find("link").text == "https://huggingface.co/Qwen/Qwen-Image-2.1"
    assert item.find("guid").text == "Qwen/Qwen-Image-2.1"


def test_render_feed_escapes():
    entries = [{"model_id": "a<b>&c", "category": "", "url": "u", "first_seen": 1}]
    xml = render_feed(FeedMeta(), entries, link="x")
    root = ET.fromstring(xml)  # must be well-formed
    assert root.find("./channel/item/title").text == "a<b>&c"


# ---- core refresher ---------------------------------------------------------

def test_refresher_respects_ttl_and_records_new(monkeypatch, tmp_path):
    calls = {"n": 0}

    def fake_fetch(api_url):
        calls["n"] += 1
        return [TrendingModel("New/Model-%d" % calls["n"], "Text Generation")]

    monkeypatch.setattr("modelwatch.core.fetch_trending", fake_fetch)
    cfg = Config(state_dir=str(tmp_path), cache_ttl_hours=24)
    r = Refresher(cfg)
    assert r.refresh_if_stale() is True
    assert calls["n"] == 1
    # Second call inside TTL: no fetch
    assert r.refresh_if_stale() is False
    assert calls["n"] == 1
    # Force overrides TTL
    assert r.refresh_if_stale(force=True) is True
    assert calls["n"] == 2
    # Model 1 recorded once, model 2 added; feed has both, newest first
    assert "<title>New/Model-2</title>" in r.feed_xml
    assert "<title>New/Model-1</title>" in r.feed_xml
    st = State(cfg.state_file)
    assert st.seen == {"New/Model-1", "New/Model-2"}
