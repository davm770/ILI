from __future__ import annotations

import re as _re
from dataclasses import dataclass, field, asdict

from .cross_platform import run_maigret
from .faces import compare, fetch_bytes
from .instagram import IGProfile, fetch_instagram
from .linkedin import LIProfile, fetch_linkedin, li_text_blob
from .reverse_image import reverse_image_linkedin_slugs
from .scoring import ScoreBreakdown, bio_overlap, combine, name_score, slug_score
from .search import Candidate, serpapi_search


@dataclass
class CandidateScore:
    url: str
    slug: str
    full_name: str
    headline: str
    score: ScoreBreakdown


@dataclass
class MatchResult:
    instagram_username: str
    instagram_full_name: str
    linkedin_url: str | None
    confidence: float
    label: str
    method: str
    score: ScoreBreakdown | None
    candidates: list[CandidateScore] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _ig_text(ig: IGProfile, extra_bios: list[str] | None = None) -> str:
    parts: list[str] = [ig.biography or ""]
    parts.extend(ig.captions[:10])
    parts.extend(ig.locations)
    parts.extend("@" + m for m in ig.mentions)
    if extra_bios:
        parts.extend(extra_bios)
    return " | ".join(parts)


def _score(ig: IGProfile, li: LIProfile, ig_face=None, use_face: bool = True,
           extra_names: list[str] | None = None, extra_bios: list[str] | None = None) -> ScoreBreakdown:
    candidate_names = [ig.full_name] + (extra_names or [])
    n = max((name_score(nm, li.full_name) for nm in candidate_names if nm), default=0.0)
    s = slug_score(ig.username, ig.full_name or (extra_names[0] if extra_names else ""), li.slug)
    b = bio_overlap(_ig_text(ig, extra_bios), li_text_blob(li))
    face_val = None
    if use_face:
        face_val = compare(ig_face, li.profile_pic_url)
    return combine(n, s, b, face_val)


def _make_cs(li: LIProfile, sc: ScoreBreakdown) -> CandidateScore:
    return CandidateScore(url=li.url, slug=li.slug, full_name=li.full_name,
                          headline=li.headline, score=sc)


def _candidate_queries(ig: IGProfile) -> list[tuple[str, bool]]:
    """Return (query, quote) pairs to try."""
    qs: list[tuple[str, bool]] = []
    if ig.full_name and len(ig.full_name.strip()) >= 3:
        qs.append((ig.full_name, True))
    # latin-only fallback if name has non-latin chars
    latin = "".join(c for c in (ig.full_name or "") if c.isascii()).strip(" |/-")
    if latin and latin != ig.full_name and len(latin) >= 3:
        qs.append((latin, True))
    # handle-based fallback
    handle_words = [w for w in ig.username.replace(".", " ").replace("_", " ").split() if len(w) >= 3]
    if handle_words:
        qs.append((" ".join(handle_words), False))
    return qs


def match(username: str, top_k: int = 5, use_face: bool = True,
          use_maigret: bool = True) -> MatchResult:
    ig = fetch_instagram(username)
    notes: list[str] = []

    # 0) Maigret cross-platform sweep (alt-names + bios + direct LI slugs)
    cps = run_maigret(ig.username) if use_maigret else None
    if cps:
        if cps.found_sites:
            notes.append(f"maigret found on {len(cps.found_sites)} sites: {cps.found_sites[:8]}")
        if cps.fullnames:
            notes.append(f"maigret alt-names: {cps.fullnames}")
        if cps.direct_linkedin_slugs:
            notes.append(f"maigret direct LI slugs: {cps.direct_linkedin_slugs}")

    # 1) bio / caption fast path
    slug = ig.linkedin_slug_from_bio()
    if slug:
        notes.append(f"linkedin slug found in bio/caption: {slug}")
        li = fetch_linkedin(slug)
        sc = _score(ig, li, ig_face=fetch_bytes(ig.profile_pic_url) if use_face else None,
                    use_face=use_face, extra_names=cps.fullnames if cps else None,
                    extra_bios=cps.bios if cps else None)
        return MatchResult(ig.username, ig.full_name, li.url,
                           confidence=max(sc.combined, 0.85), label="confident",
                           method="bio_link", score=sc, candidates=[_make_cs(li, sc)], notes=notes)

    # 1b) direct LI slug from any cross-platform profile (linktr.ee, soundcloud, etc.)
    if cps and cps.direct_linkedin_slugs:
        slug = cps.direct_linkedin_slugs[0]
        notes.append(f"using LI slug from maigret: {slug}")
        li = fetch_linkedin(slug)
        sc = _score(ig, li, ig_face=fetch_bytes(ig.profile_pic_url) if use_face else None,
                    use_face=use_face, extra_names=cps.fullnames, extra_bios=cps.bios)
        return MatchResult(ig.username, ig.full_name, li.url,
                           confidence=max(sc.combined, 0.85), label="confident",
                           method="cross_platform", score=sc, candidates=[_make_cs(li, sc)], notes=notes)

    # 2) external link (linktr.ee etc.) one-hop
    slug = ig.linkedin_slug_from_external()
    if slug:
        notes.append(f"linkedin slug found via external link follow: {slug}")
        li = fetch_linkedin(slug)
        sc = _score(ig, li, ig_face=fetch_bytes(ig.profile_pic_url) if use_face else None,
                    use_face=use_face, extra_names=cps.fullnames if cps else None,
                    extra_bios=cps.bios if cps else None)
        return MatchResult(ig.username, ig.full_name, li.url,
                           confidence=max(sc.combined, 0.85), label="confident",
                           method="external_link", score=sc, candidates=[_make_cs(li, sc)], notes=notes)

    # 3) reverse image search of profile pic
    if ig.profile_pic_url:
        ri_slugs = reverse_image_linkedin_slugs(ig.profile_pic_url)
        if ri_slugs:
            notes.append(f"reverse image search hits: {ri_slugs}")
            li = fetch_linkedin(ri_slugs[0])
            sc = _score(ig, li, ig_face=fetch_bytes(ig.profile_pic_url) if use_face else None,
                        use_face=use_face, extra_names=cps.fullnames if cps else None,
                        extra_bios=cps.bios if cps else None)
            return MatchResult(ig.username, ig.full_name, li.url,
                               confidence=max(sc.combined, 0.85), label="confident",
                               method="reverse_image", score=sc, candidates=[_make_cs(li, sc)], notes=notes)

    # 4) search-based candidates (multi-query)
    # Prefer Maigret-discovered fullnames first when IG full_name is weak (empty,
    # initials, or has non-latin/emoji chars); otherwise IG name first.
    ig_queries = _candidate_queries(ig)
    maigret_queries: list[tuple[str, bool]] = []
    if cps and cps.fullnames:
        for nm in cps.fullnames:
            if len(nm.split()) >= 2 and any(c.isalpha() for c in nm):
                maigret_queries.append((nm, True))
    ig_tokens = _re.findall(r"[A-Za-z]{3,}", ig.full_name or "")
    ig_name_weak = len(ig_tokens) < 2
    queries = (maigret_queries + ig_queries) if ig_name_weak else (ig_queries + maigret_queries)
    seen_q: set[str] = set()
    queries = [(q, qu) for (q, qu) in queries if not (q.lower() in seen_q or seen_q.add(q.lower()))]

    if not queries:
        notes.append("no usable query: empty IG full_name, short handle, no maigret names")
        return MatchResult(ig.username, ig.full_name, None, 0.0, "reject",
                           "no_match", None, [], notes)

    # Take top-3 per query so a weak first query can't crowd out a strong later one.
    per_query_cap = 3
    all_cands: dict[str, Candidate] = {}
    for q, quote in queries:
        for c in serpapi_search(q, quote=quote)[:per_query_cap]:
            all_cands.setdefault(c.slug, c)
    cands = list(all_cands.values())[: top_k + 3]
    notes.append(f"queries used: {[q for q,_ in queries]}")
    notes.append(f"search candidates: {[c.slug for c in cands]}")

    ig_face = fetch_bytes(ig.profile_pic_url) if use_face else None
    if use_face and ig_face is None:
        notes.append("no face detected in IG profile pic; face scoring disabled")

    extra_names = cps.fullnames if cps else None
    extra_bios = cps.bios if cps else None
    scored: list[CandidateScore] = []
    for c in cands:
        try:
            li = fetch_linkedin(c.slug)
        except Exception as e:
            notes.append(f"enrich failed for {c.slug}: {e}")
            continue
        sc = _score(ig, li, ig_face=ig_face, use_face=use_face and ig_face is not None,
                    extra_names=extra_names, extra_bios=extra_bios)
        scored.append(_make_cs(li, sc))

    if not scored:
        return MatchResult(ig.username, ig.full_name, None, 0.0, "reject",
                           "no_match", None, [], notes)

    # Tie-break: among candidates with near-perfect name+slug, prefer those whose
    # face was actually verified (face > 0). Photo-less candidates get a free pass
    # in the no-face scoring formula, so we must demote them when a face-matched
    # sibling exists.
    tied = [c for c in scored if c.score.name >= 0.9 and c.score.slug >= 0.9]
    face_tied = [c for c in tied if c.score.face > 0]
    if len(tied) >= 2 and face_tied:
        # rerank: face-verified first (by face desc), then the rest by combined
        face_tied.sort(key=lambda c: c.score.face, reverse=True)
        rest = [c for c in scored if c not in face_tied]
        rest.sort(key=lambda c: c.score.combined, reverse=True)
        scored = face_tied + rest
    else:
        scored.sort(key=lambda c: c.score.combined, reverse=True)

    best = scored[0]
    runner = scored[1].score.combined if len(scored) > 1 else 0.0
    margin = best.score.combined - runner

    conf = best.score.combined
    if best.score.face >= 0.70:
        conf = max(conf, 0.85)
    if best.score.name >= 0.9 and best.score.slug >= 0.9 and margin >= 0.15:
        conf = max(conf, 0.80)
    elif best.score.name >= 0.85 and margin >= 0.20:
        conf = max(conf, 0.70)

    label = "confident" if conf >= 0.65 else ("uncertain" if conf >= 0.45 else "reject")

    return MatchResult(ig.username, ig.full_name, best.url, conf, label,
                       "search+score", best.score, scored, notes)
