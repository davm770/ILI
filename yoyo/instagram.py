from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import requests

LINKEDIN_RE = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/([A-Za-z0-9\-_%]+)/?", re.I)
MENTION_RE = re.compile(r"@([A-Za-z0-9_.]{2,30})")
URL_RE = re.compile(r"https?://[^\s)>\"']+", re.I)
SCRAPINGDOG_URL = "https://api.scrapingdog.com/instagram/profile"


@dataclass
class IGProfile:
    username: str
    full_name: str
    biography: str
    external_url: str | None
    bio_links: list[str]
    profile_pic_url: str
    followers: int
    captions: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)

    def linkedin_slug_from_bio(self) -> str | None:
        haystacks = [self.biography or "", self.external_url or "", *self.bio_links, *self.captions]
        for text in haystacks:
            m = LINKEDIN_RE.search(text)
            if m:
                return m.group(1).rstrip("/")
        return None

    def linkedin_slug_from_external(self, timeout: int = 10) -> str | None:
        """Follow bio_links (linktr.ee, beacons, personal sites) one hop and scan body for LinkedIn URL."""
        for raw in self.bio_links:
            url = raw
            try:
                m = re.match(r"https?://l\.instagram\.com/.*[?&]u=([^&]+)", url)
                if m:
                    from urllib.parse import unquote
                    url = unquote(m.group(1))
                r = requests.get(url, timeout=timeout, allow_redirects=True,
                                 headers={"User-Agent": "Mozilla/5.0"})
                hit = LINKEDIN_RE.search(r.text)
                if hit:
                    return hit.group(1).rstrip("/")
            except Exception:
                continue
        return None


def fetch_instagram(username: str, api_key: str | None = None) -> IGProfile:
    api_key = api_key or os.environ["SCRAPINGDOG_API_KEY"]
    r = requests.get(SCRAPINGDOG_URL, params={"api_key": api_key, "username": username}, timeout=30)
    r.raise_for_status()
    d = r.json()
    if not d.get("username"):
        raise RuntimeError(f"ScrapingDog returned no profile for {username}: {d}")

    bio_links: list[str] = []
    for b in d.get("bio_links") or []:
        if isinstance(b, dict) and b.get("url"):
            bio_links.append(b["url"])

    captions: list[str] = []
    mentions: list[str] = []
    locations: list[str] = []
    tl = d.get("owner_to_timeline_media") or {}
    for m in (tl.get("media") or []):
        if not isinstance(m, dict):
            continue
        cap = m.get("caption")
        if isinstance(cap, str) and cap:
            captions.append(cap)
            mentions.extend(MENTION_RE.findall(cap))
        loc = m.get("location")
        if isinstance(loc, dict) and loc.get("name"):
            locations.append(loc["name"])

    return IGProfile(
        username=d["username"],
        full_name=d.get("full_name") or "",
        biography=d.get("bio") or "",
        external_url=d.get("external_url"),
        bio_links=bio_links,
        profile_pic_url=d.get("profile_pic_url_hd") or d.get("profile_pic_url") or "",
        followers=int(d.get("followers_count") or 0),
        captions=captions,
        mentions=list(dict.fromkeys(mentions)),  # dedupe preserving order
        locations=locations,
    )
