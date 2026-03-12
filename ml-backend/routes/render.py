"""Render route — text → handwriting image."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import io, logging, numpy as np
from PIL import Image

router = APIRouter()
logger = logging.getLogger(__name__)

_model = None

def get_model():
    global _model
    if _model is None:
        from models.handwriting_model import HandwritingSynthesizer
        _model = HandwritingSynthesizer()
    return _model


class RenderRequest(BaseModel):
    text: str
    line_width: int = 800
    ink_color: str = "#1a1714"     # hex color
    paper_style: str = "lined"    # lined | blank | grid | dotted
    font_size: int = 24


@router.post("")
async def render_text(req: RenderRequest):
    """Render text as a handwriting PNG image."""
    if not req.text.strip():
        raise HTTPException(400, "Text cannot be empty")
    if len(req.text) > 2000:
        raise HTTPException(400, "Text too long (max 2000 chars)")

    try:
        model = get_model()
        img_array = model.render_text(req.text, line_width_px=req.line_width)

        # Apply ink color
        img_array = _apply_ink_color(img_array, req.ink_color)

        # Apply paper background
        img_array = _apply_paper(img_array, req.paper_style)

        # Encode to PNG
        img = Image.fromarray(img_array)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)

        return StreamingResponse(buf, media_type="image/png",
                                  headers={"Content-Disposition": "inline; filename=handwriting.png"})

    except Exception as e:
        logger.error(f"Render failed: {e}")
        # Fallback: return the text as JSON (frontend will display in CSS font)
        return {"text": req.text, "fallback": True}


def _apply_ink_color(img: np.ndarray, hex_color: str) -> np.ndarray:
    """Replace black ink with the specified color."""
    try:
        hex_color = hex_color.lstrip("#")
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        r, g, b = 26, 23, 20

    colored = img.copy()
    mask = (img[:, :, 0] < 128)  # ink pixels
    colored[mask, 0] = r
    colored[mask, 1] = g
    colored[mask, 2] = b
    return colored


def _apply_paper(img: np.ndarray, style: str) -> np.ndarray:
    """Add paper lines/grid to background."""
    h, w = img.shape[:2]
    line_color = np.array([200, 210, 230], dtype=np.uint8)  # light blue lines

    if style == "lined":
        for y in range(32, h, 32):
            img[y:y+1, :] = np.where(img[y:y+1, :] > 200, line_color, img[y:y+1, :])

    elif style == "grid":
        for y in range(32, h, 32):
            img[y:y+1, :] = np.where(img[y:y+1, :] > 200, line_color, img[y:y+1, :])
        for x in range(32, w, 32):
            img[:, x:x+1] = np.where(img[:, x:x+1] > 200, line_color, img[:, x:x+1])

    elif style == "dotted":
        for y in range(32, h, 32):
            for x in range(32, w, 32):
                if img[y, x, 0] > 200:
                    img[y, x] = line_color

    return img
