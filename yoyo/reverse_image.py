from __future__ import annotations

import os
import re

import requests

LINKEDIN_RE = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/([A-Za-z0-9\-_%]+)", re.I)


def reverse_image_linkedin_slugs(image_url: str, api_key: str | None = None) -> list[str]:
    """Run Google reverse image search via SerpAPI; return any LinkedIn slugs found."""
    api_key = api_key or os.environ["SERPAPI_API_KEY"]
    try:
        r = requests.get(
            "https://serpapi.com/search.json",
            params={"engine": "google_reverse_image", "image_url": image_url, "api_key": api_key},
            timeout=45,
        )
        d = r.json()
    except Exception:
        return []
    slugs: list[str] = []
    seen: set[str] = set()
    blob = []
    for key in ("image_results", "inline_images", "knowledge_graph", "search_information",
                "related_searches", "organic_results"):
        v = d.get(key)
        if v is not None:
            blob.append(str(v))
    text = "\n".join(blob)
    for m in LINKEDIN_RE.finditer(text):
        s = m.group(1).rstrip("/").lower()
        if s in seen:
            continue
        seen.add(s)
        slugs.append(s)
    return slugs
