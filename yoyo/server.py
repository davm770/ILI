from __future__ import annotations

import os
import traceback
from dataclasses import asdict

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

load_dotenv()

from .match import match
from .photo_match import get_image, match_by_photo

app = FastAPI(title="yoyo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("YOYO_CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


_DEFAULT_FACE = os.environ.get("YOYO_USE_FACE", "1") not in ("0", "false", "False", "")
_DEFAULT_MAIGRET = os.environ.get("YOYO_USE_MAIGRET", "1") not in ("0", "false", "False", "")


@app.get("/match/{username}")
def do_match(username: str, use_face: bool | None = None, use_maigret: bool | None = None):
    try:
        r = match(
            username,
            use_face=_DEFAULT_FACE if use_face is None else use_face,
            use_maigret=_DEFAULT_MAIGRET if use_maigret is None else use_maigret,
        )
        return asdict(r)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.get("/uploads/{key}")
def serve_upload(key: str):
    v = get_image(key)
    if not v:
        raise HTTPException(status_code=404, detail="expired or unknown")
    data, ct = v
    return Response(content=data, media_type=ct)


@app.post("/match-photo")
async def do_match_photo(request: Request, file: UploadFile = File(...)):
    data = await file.read()
    if not data or len(data) < 1024:
        raise HTTPException(status_code=400, detail="image too small")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="image too large (>8MB)")
    public_base = os.environ.get("YOYO_PUBLIC_BASE_URL") or str(request.base_url).rstrip("/")
    try:
        result = match_by_photo(data, public_base_url=public_base, content_type=file.content_type or "image/jpeg")
        return result.to_dict()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("yoyo.server:app", host="0.0.0.0",
                port=int(os.environ.get("PORT", 8000)), reload=False)
