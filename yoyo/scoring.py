from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

_TOKEN_RE = re.compile(r"[A-Za-z]{2,}")
_STOPWORDS = {"the", "and", "for", "with", "from", "this", "that", "her", "his",
              "are", "was", "you", "your", "our", "out", "all", "but", "not",
              "of", "in", "at", "to", "is", "it", "an", "as", "be", "or"}
_CITY_ALIASES = {
    "nyc": {"new", "york"},
    "ny": {"new", "york"},
    "sf": {"san", "francisco"},
    "la": {"los", "angeles"},
    "uk": {"united", "kingdom"},
    "usa": {"united", "states"},
}


def _tokens(s: str) -> set[str]:
    raw = {t.lower() for t in _TOKEN_RE.findall(s or "")}
    raw -= _STOPWORDS
    expanded = set(raw)
    for tok in raw:
        if tok in _CITY_ALIASES:
            expanded |= _CITY_ALIASES[tok]
    return expanded


def name_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return fuzz.token_set_ratio(a.lower(), b.lower()) / 100.0


def slug_score(ig_username: str, ig_full_name: str, li_slug: str) -> float:
    li = li_slug.replace("-", "").replace("_", "").lower()
    cand_keys = [
        ig_username.lower(),
        ig_full_name.lower().replace(" ", ""),
        "".join(w[0] for w in ig_full_name.split()) if ig_full_name else "",
    ]
    return max((fuzz.partial_ratio(k, li) / 100.0) for k in cand_keys if k)


def bio_overlap(ig_bio: str, li_blob: str) -> float:
    a, b = _tokens(ig_bio), _tokens(li_blob)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a)


@dataclass
class ScoreBreakdown:
    name: float
    slug: float
    bio: float
    face: float
    combined: float

    def label(self) -> str:
        if self.combined >= 0.65:
            return "confident"
        if self.combined >= 0.45:
            return "uncertain"
        return "reject"


def combine(name: float, slug: float, bio: float, face: float | None) -> ScoreBreakdown:
    if face is None:
        # redistribute the 0.50 face weight: name 0.40, slug 0.20, bio 0.40
        combined = 0.40 * name + 0.20 * slug + 0.40 * bio
        face_val = 0.0
    else:
        combined = 0.50 * face + 0.20 * name + 0.10 * slug + 0.20 * bio
        face_val = face
    return ScoreBreakdown(name=name, slug=slug, bio=bio, face=face_val, combined=combined)
