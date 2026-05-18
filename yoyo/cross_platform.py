from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

LINKEDIN_RE = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/([A-Za-z0-9\-_%]+)", re.I)


@dataclass
class CrossPlatformSignals:
    fullnames: list[str] = field(default_factory=list)   # alternative names found on other platforms
    bios: list[str] = field(default_factory=list)        # bio strings to merge into bio_overlap
    direct_linkedin_slugs: list[str] = field(default_factory=list)  # explicit LI slugs found on other platforms
    found_sites: list[str] = field(default_factory=list)


def _walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)


def _maigret_bin() -> str | None:
    cand = os.path.join(os.path.dirname(sys.executable), "maigret")
    if os.path.isfile(cand) and os.access(cand, os.X_OK):
        return cand
    return shutil.which("maigret")


def run_maigret(username: str, top_sites: int = 200, timeout_s: int = 240) -> CrossPlatformSignals:
    out = CrossPlatformSignals()
    binpath = _maigret_bin()
    if binpath is None:
        return out
    with tempfile.TemporaryDirectory() as td:
        try:
            subprocess.run(
                [binpath, username, "--no-progressbar", "--top-sites", str(top_sites),
                 "-T", "--timeout", "8", "-n", "30", "--no-recursion",
                 "-J", "simple", "--folderoutput", td],
                capture_output=True, timeout=timeout_s, text=True,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return out

        import glob, os
        paths = glob.glob(os.path.join(td, "*_simple.json"))
        if not paths:
            return out
        try:
            data = json.loads(open(paths[0]).read())
        except Exception:
            return out

    seen_names: set[str] = set()
    seen_slugs: set[str] = set()
    for site_name, entry in (data or {}).items():
        status = entry.get("status") or {}
        if status.get("status") != "Claimed":
            continue
        out.found_sites.append(site_name)
        ids = status.get("ids") or {}

        fn = ids.get("fullname")
        if isinstance(fn, str) and fn.strip():
            cleaned = fn.strip().lower()
            if cleaned not in seen_names and len(cleaned) >= 3:
                seen_names.add(cleaned)
                out.fullnames.append(fn.strip())

        for k in ("bio", "summary", "description", "headline"):
            v = ids.get(k)
            if isinstance(v, str) and v.strip():
                out.bios.append(v.strip())

        # scan every string field for LinkedIn URLs
        for s in _walk_strings(entry):
            for m in LINKEDIN_RE.finditer(s):
                slug = m.group(1).rstrip("/").lower()
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                out.direct_linkedin_slugs.append(slug)

    return out
