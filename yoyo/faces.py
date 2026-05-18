from __future__ import annotations

import io
from functools import lru_cache

import numpy as np
import requests
from PIL import Image

_HEADERS = {"User-Agent": "Mozilla/5.0"}


@lru_cache(maxsize=1)
def _app():
    import insightface
    from insightface.app import FaceAnalysis
    a = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    a.prepare(ctx_id=-1, det_size=(640, 640))
    return a


def _img(url: str) -> np.ndarray | None:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=30, headers=_HEADERS)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        return np.array(im)[:, :, ::-1]  # RGB -> BGR for insightface
    except Exception:
        return None


def embed(url: str) -> np.ndarray | None:
    arr = _img(url)
    if arr is None:
        return None
    try:
        faces = _app().get(arr)
    except Exception:
        return None
    if not faces:
        return None
    faces.sort(key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]), reverse=True)
    return faces[0].normed_embedding


def cosine(a: np.ndarray | None, b: np.ndarray | None) -> float | None:
    if a is None or b is None:
        return None
    sim = float(np.dot(a, b))
    return (sim + 1.0) / 2.0  # map [-1,1] to [0,1]
