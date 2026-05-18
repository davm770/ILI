from __future__ import annotations

import os
import re
from dataclasses import dataclass

import requests

LINKEDIN_IN_RE = re.compile(r"https?://([a-z]{2,3}\.)?linkedin\.com/in/([A-Za-z0-9\-_%]+)/?", re.I)


@dataclass
class Candidate:
    url: str
    slug: str
    title: str
    snippet: str
    rank: int


def _normalize(url: str) -> tuple[str, str] | None:
    m = LINKEDIN_IN_RE.search(url)
    if not m:
        return None
    slug = m.group(2).rstrip("/").lower()
    return f"https://www.linkedin.com/in/{slug}", slug


def serpapi_search(query: str, api_key: str | None = None, num: int = 10,
                   quote: bool = True) -> list[Candidate]:
    api_key = api_key or os.environ["SERPAPI_API_KEY"]
    q_arg = f'"{query}"' if quote else query
    q = f"site:linkedin.com/in {q_arg}"
    r = requests.get(
        "https://serpapi.com/search.json",
        params={"engine": "google", "q": q, "num": num, "api_key": api_key},
        timeout=30,
    )
    r.raise_for_status()
    out: list[Candidate] = []
    seen: set[str] = set()
    for item in r.json().get("organic_results", []):
        url = item.get("link") or ""
        norm = _normalize(url)
        if not norm:
            continue
        canonical, slug = norm
        if slug in seen:
            continue
        seen.add(slug)
        out.append(Candidate(
            url=canonical,
            slug=slug,
            title=item.get("title") or "",
            snippet=item.get("snippet") or "",
            rank=item.get("position") or len(out) + 1,
        ))
    return out
