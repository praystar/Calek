"""
HandScribe ML Backend
FastAPI server exposing endpoints for:
 - Corpus analysis & character extraction
 - Missing glyph synthesis
 - Text-to-handwriting rendering
 - Audio transcription (Whisper)
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import logging
import os
from dotenv import load_dotenv

load_dotenv()

from routes.corpus import router as corpus_router
from routes.render import router as render_router
from routes.transcribe import router as transcribe_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="HandScribe API",
    description="ML backend for personal handwriting synthesis",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("CORS_ORIGIN", "http://localhost:3000"),
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(corpus_router, prefix="/corpus", tags=["Corpus"])
app.include_router(render_router, prefix="/render", tags=["Render"])
app.include_router(transcribe_router, prefix="/transcribe", tags=["Transcribe"])


@app.get("/")
async def root():
    return {"status": "ok", "service": "HandScribe API", "version": "1.0.0"}


@app.get("/health")
async def health():
    import torch
    return {
        "status": "healthy",
        "cuda_available": torch.cuda.is_available(),
        "device": "cuda" if torch.cuda.is_available() else "cpu"
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
