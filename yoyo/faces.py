from __future__ import annotations

import os
from functools import lru_cache

import boto3
import requests
from botocore.exceptions import ClientError

_HEADERS = {"User-Agent": "Mozilla/5.0"}


@lru_cache(maxsize=1)
def _rekog():
    return boto3.client("rekognition", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def fetch_bytes(url: str | None) -> bytes | None:
    if not url:
        return None
    try:
        r = requests.get(url, headers=_HEADERS, timeout=20)
        r.raise_for_status()
        return r.content
    except Exception:
        return None


def compare(source_bytes: bytes | None, target_url: str | None) -> float | None:
    """Return similarity in [0,1] between source face and target image, or None if either has no face / fetch failed."""
    if source_bytes is None:
        return None
    target = fetch_bytes(target_url)
    if target is None:
        return None
    try:
        resp = _rekog().compare_faces(
            SourceImage={"Bytes": source_bytes},
            TargetImage={"Bytes": target},
            SimilarityThreshold=0,
        )
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        # InvalidParameterException = no face detected in one of the images
        if code in ("InvalidParameterException", "InvalidImageFormatException", "ImageTooLargeException"):
            return None
        raise
    except Exception:
        return None
    matches = resp.get("FaceMatches") or []
    if not matches:
        return 0.0
    return float(matches[0]["Similarity"]) / 100.0
