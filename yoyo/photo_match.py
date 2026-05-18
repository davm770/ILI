from __future__ import annotations

import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict

import requests

from .faces import compare
from .linkedin import fetch_linkedin

LINKEDIN_RE = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/([A-Za-z0-9\-_%]+)", re.I)

# In-memory store for uploaded images, expiring after 5 min.
_UPLOADS: dict[str, tuple[bytes, str, float]] = {}
_LOCK = threading.Lock()


def stash_image(data: bytes, content_type: str = "image/jpeg") -> str:
    key = uuid.uuid4().hex
    with _LOCK:
        _UPLOADS[key] = (data, content_type, time.time() + 300)
        # opportunistic cleanup
        now = time.time()
        for k in list(_UPLOADS):
            if _UPLOADS[k][2] < now:
                del _UPLOADS[k]
    return key


def get_image(key: str) -> tuple[bytes, str] | None:
    with _LOCK:
        v = _UPLOADS.get(key)
    if not v:
        return None
    data, ct, exp = v
    if exp < time.time():
        with _LOCK:
            _UPLOADS.pop(key, None)
        return None
    return data, ct


def _serpapi_collect_linkedin_slugs(engine: str, image_url: str) -> list[str]:
    key = os.environ.get("SERPAPI_API_KEY")
    if not key:
        return []
    try:
        r = requests.get(
            "https://serpapi.com/search.json",
            params={"engine": engine, "url": image_url, "api_key": key},
            timeout=60,
        )
        d = r.json()
    except Exception:
        return []
    blob = []
    for v in d.values():
        blob.append(str(v))
    text = "\n".join(blob)
    seen: set[str] = set()
    out: list[str] = []
    for m in LINKEDIN_RE.finditer(text):
        s = m.group(1).rstrip("/").lower()
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


@dataclass
class PhotoCandidate:
    linkedin_url: str
    slug: str
    full_name: str
    headline: str
    face_similarity: float | None
    source: str  # "lens" | "reverse_image"


@dataclass
class PhotoMatchResult:
    candidates: list[PhotoCandidate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def match_by_photo(image_bytes: bytes, public_base_url: str, content_type: str = "image/jpeg") -> PhotoMatchResult:
    """Run SerpAPI Lens + reverse_image on the uploaded photo, then rank LinkedIn hits by face similarity."""
    notes: list[str] = []
    key = stash_image(image_bytes, content_type)
    image_url = f"{public_base_url.rstrip('/')}/uploads/{key}"

    lens_slugs = _serpapi_collect_linkedin_slugs("google_lens", image_url)
    ri_slugs = _serpapi_collect_linkedin_slugs("google_reverse_image", image_url)
    notes.append(f"google_lens slugs: {lens_slugs}")
    notes.append(f"google_reverse_image slugs: {ri_slugs}")

    # merge, preserving source attribution; lens first
    seen: set[str] = set()
    ordered: list[tuple[str, str]] = []
    for s in lens_slugs:
        if s in seen:
            continue
        seen.add(s); ordered.append((s, "lens"))
    for s in ri_slugs:
        if s in seen:
            continue
        seen.add(s); ordered.append((s, "reverse_image"))

    cands: list[PhotoCandidate] = []
    for slug, source in ordered[:8]:
        try:
            li = fetch_linkedin(slug)
        except Exception as e:
            notes.append(f"enrich failed for {slug}: {e}")
            continue
        face = compare(image_bytes, li.profile_pic_url) if li.profile_pic_url else None
        cands.append(PhotoCandidate(
            linkedin_url=li.url, slug=li.slug, full_name=li.full_name,
            headline=li.headline, face_similarity=face, source=source,
        ))

    cands.sort(key=lambda c: c.face_similarity or 0, reverse=True)
    return PhotoMatchResult(candidates=cands, notes=notes)
