"""Fetch the trending model list and pipeline-tag labels from Hugging Face."""

from __future__ import annotations

import requests
from dataclasses import dataclass

HF_LINK = "https://huggingface.co/{model_id}"
TAGS_URL = "https://huggingface.co/api/models-tags-by-type"
USER_AGENT = "modelwatch/0.1 (+https://github.com/nkavassalis/modelwatch)"


@dataclass
class TrendingModel:
    model_id: str
    category: str  # human readable pipeline label, "" when unknown

    @property
    def url(self) -> str:
        return HF_LINK.format(model_id=self.model_id)


def _humanize(tag: str) -> str:
    """Fallback label: text-to-image -> Text-to-Image,
    automatic-speech-recognition -> Automatic Speech Recognition."""
    parts = tag.split("-")
    out = parts[0].capitalize()
    prev_to = False
    for part in parts[1:]:
        if part == "to":
            out += "-to"
            prev_to = True
        else:
            out += ("-" if prev_to else " ") + part.capitalize()
            prev_to = False
    return out


def fetch_trending(api_url: str, timeout: int = 30) -> list[TrendingModel]:
    """Return the current trending list in rank order."""
    resp = requests.get(
        api_url, timeout=timeout, headers={"User-Agent": USER_AGENT}
    )
    resp.raise_for_status()
    labels = fetch_pipeline_labels(timeout=timeout)
    models: list[TrendingModel] = []
    for item in resp.json():
        model_id = item.get("id") or item.get("modelId")
        if not model_id:
            continue
        tag = item.get("pipeline_tag") or ""
        models.append(TrendingModel(model_id, labels.get(tag, _humanize(tag) if tag else "")))
    return models


def fetch_pipeline_labels(timeout: int = 30) -> dict[str, str]:
    """Map pipeline_tag ids to human labels ("text-to-image" -> "Text-to-Image")."""
    try:
        resp = requests.get(
            TAGS_URL, timeout=timeout, headers={"User-Agent": USER_AGENT}
        )
        resp.raise_for_status()
        return {
            t["id"]: t["label"]
            for t in resp.json().get("pipeline_tag", [])
            if "id" in t and "label" in t
        }
    except Exception:
        return {}
