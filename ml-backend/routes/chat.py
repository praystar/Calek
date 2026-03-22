"""
Chat route — proxies Gemini with server-side rate limiting + auto-retry.
One request in flight at a time. 429s are retried with backoff silently.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import httpx, asyncio, logging, os, time

router = APIRouter()
logger = logging.getLogger(__name__)

GEMINI_MODEL  = "gemini-2.0-flash-lite"   # 30 RPM free vs 15 RPM for flash
GEMINI_URL    = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
MIN_INTERVAL  = 6.0    # seconds between dispatches — 10/min, well under 15 RPM
MAX_TOKENS    = 350
MAX_HISTORY   = 4      # keep payload small
MAX_RETRIES   = 4      # retry 429s up to 4 times
RETRY_DELAYS  = [5, 10, 20, 40]   # seconds to wait before each retry

_lock      = asyncio.Lock()
_last_sent = 0.0


class Message(BaseModel):
    role:    str
    content: str

class ChatRequest(BaseModel):
    message:  str
    history:  List[Message] = []
    api_key:  str = ""


@router.post("")
async def chat(req: ChatRequest):
    api_key = os.getenv("GEMINI_API_KEY", "").strip() or req.api_key.strip()
    if not api_key:
        raise HTTPException(400, "No Gemini API key. Set GEMINI_API_KEY in ml-backend/.env or enter it in the UI.")
    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty.")

    # ── Enforce minimum interval between dispatches ───────────────────────────
    async with _lock:
        global _last_sent
        now  = time.monotonic()
        wait = MIN_INTERVAL - (now - _last_sent)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_sent = time.monotonic()

        # ── Build payload ─────────────────────────────────────────────────────
        recent   = req.history[-MAX_HISTORY:]
        contents = [
            {"role": "user" if m.role == "user" else "model",
             "parts": [{"text": m.content}]}
            for m in recent
        ]
        contents.append({"role": "user", "parts": [{"text": req.message}]})

        payload = {
            "contents": contents,
            "generationConfig": {"temperature": 0.85, "maxOutputTokens": MAX_TOKENS},
        }

        # ── Call Gemini with retry on 429 ─────────────────────────────────────
        last_err = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(f"{GEMINI_URL}?key={api_key}", json=payload)

                if resp.status_code == 200:
                    data  = resp.json()
                    text  = data["candidates"][0]["content"]["parts"][0]["text"]
                    return {"reply": text}

                if resp.status_code == 429:
                    delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    logger.warning(f"Gemini 429 on attempt {attempt+1}, retrying in {delay}s…")
                    await asyncio.sleep(delay)
                    _last_sent = time.monotonic()   # reset interval after sleeping
                    last_err   = "Rate limit"
                    continue

                if resp.status_code == 400:
                    detail = resp.json().get("error", {}).get("message", "Bad request")
                    if "API_KEY" in detail or "API_key" in detail:
                        raise HTTPException(400, "Invalid Gemini API key — check aistudio.google.com.")
                    raise HTTPException(400, detail)

                raise HTTPException(502, f"Gemini returned {resp.status_code}")

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Gemini request error: {e}")
                last_err = str(e)
                await asyncio.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])

        raise HTTPException(429,
            "Gemini free tier is busy. All retries exhausted — please wait 1–2 minutes and try again. "
            "Consider upgrading to a paid Gemini key for unlimited access.")
