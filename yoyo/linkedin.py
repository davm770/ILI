from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests

SCRAPINGDOG_URL = "https://api.scrapingdog.com/linkedin"


@dataclass
class LIProfile:
    url: str
    slug: str
    full_name: str
    headline: str
    location: str
    company: str
    profile_pic_url: str
    raw: dict


def _flatten_text(d: dict) -> str:
    parts: list[str] = []
    for k in ("headline", "summary", "about", "location", "city", "country"):
        v = d.get(k)
        if isinstance(v, str):
            parts.append(v)
    desc = d.get("description")
    if isinstance(desc, dict):
        for v in desc.values():
            if isinstance(v, str) and not v.startswith("http"):
                parts.append(v)
    for exp in (d.get("experience") or []):
        if isinstance(exp, dict):
            for k in ("company_name", "position", "summary", "location"):
                v = exp.get(k)
                if isinstance(v, str):
                    parts.append(v)
    for edu in (d.get("education") or []):
        if isinstance(edu, dict):
            for k in ("college_name", "college_degree", "college_degree_field"):
                v = edu.get(k)
                if isinstance(v, str):
                    parts.append(v)
    return " | ".join(parts)


def fetch_linkedin(slug: str, api_key: str | None = None, premium: bool = True,
                   max_wait_s: int = 240) -> LIProfile:
    api_key = api_key or os.environ["SCRAPINGDOG_API_KEY"]
    deadline = time.time() + max_wait_s
    last: dict | None = None
    while True:
        r = requests.get(
            SCRAPINGDOG_URL,
            params={"api_key": api_key, "type": "profile", "linkId": slug,
                    "premium": "true" if premium else "false"},
            timeout=60,
        )
        try:
            d = r.json()
        except Exception:
            d = {"_raw": r.text[:500], "status": r.status_code}
        if isinstance(d, list) and d:
            d = d[0]
        if isinstance(d, dict) and d.get("first_name") is not None:
            full = " ".join(x for x in (d.get("first_name"), d.get("last_name")) if x).strip()
            exp_list = d.get("experience") or []
            company = ""
            if exp_list and isinstance(exp_list[0], dict):
                company = exp_list[0].get("company_name") or ""
            loc = d.get("location") or d.get("city") or ""
            pic = d.get("profile_photo") or d.get("profile_picture") or d.get("background_cover_image_url") or ""
            return LIProfile(
                url=f"https://www.linkedin.com/in/{slug}",
                slug=slug,
                full_name=full,
                headline=d.get("headline") or "",
                location=loc,
                company=company,
                profile_pic_url=pic,
                raw=d,
            )
        last = d
        if time.time() > deadline:
            raise RuntimeError(f"ScrapingDog LinkedIn timeout for {slug}: {last}")
        time.sleep(8)


def li_text_blob(p: LIProfile) -> str:
    return _flatten_text(p.raw)
