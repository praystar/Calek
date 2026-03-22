"""
Render route — text → handwriting PNG using real extracted glyph images.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from pathlib import Path
import io, logging, json, random
import numpy as np
import cv2
from PIL import Image

router  = APIRouter()
logger  = logging.getLogger(__name__)

# Absolute paths — safe regardless of where uvicorn was started
_HERE       = Path(__file__).parent.parent          # ml-backend/
GLYPH_DIR   = _HERE / "data" / "user_glyphs"
STYLE_FILE  = GLYPH_DIR / "style.json"

GLYPH_SIZE  = 64    # must match CharacterExtractor.glyph_size
MARGIN      = 40    # px around the page
LINE_GAP    = 24    # px between text lines
CHAR_GAP    = 4     # px between characters (small fixed gap, NOT style spacing)


def _load_font_synth():
    from utils.font_synthesizer import FontSynthesizer
    return FontSynthesizer()


def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    try:
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return (26, 23, 20)


def _load_glyph_library() -> dict:
    """Load all saved glyph PNGs keyed by character."""
    library: dict = {}
    if not GLYPH_DIR.exists():
        return library
    for f in GLYPH_DIR.glob("*.png"):
        try:
            codepoint = int(f.stem.split("_")[0])
            if codepoint > 0xFFFF:
                continue  # skip hash-keyed placeholders
            char = chr(codepoint)
            img = np.array(Image.open(f).convert("L"), dtype=np.float32) / 255.0

            # Auto-fix inversion: ink should be bright (high values), paper dark.
            # If the image is mostly bright (mean > 0.6), it's paper-white — invert it.
            if np.mean(img) > 0.6:
                img = 1.0 - img

            # Reject glyphs that are nearly blank or nearly solid — bad extractions
            ink_ratio = np.mean(img)
            if ink_ratio < 0.02 or ink_ratio > 0.95:
                continue

            library.setdefault(char, []).append(img)
        except Exception:
            pass
    return library


def _load_style() -> dict:
    if STYLE_FILE.exists():
        try:
            return json.loads(STYLE_FILE.read_text())
        except Exception:
            pass
    return {}


def _render(text: str, canvas_width: int, ink_rgb: tuple, paper_style: str) -> np.ndarray:
    glyph_lib  = _load_glyph_library()
    style      = _load_style()
    font_synth = None

    char_w = GLYPH_SIZE
    char_h = GLYPH_SIZE
    line_h = char_h + LINE_GAP

    # How many chars fit per line
    usable_width   = canvas_width - 2 * MARGIN
    chars_per_line = max(1, usable_width // (char_w + CHAR_GAP))

    # Word-wrap
    words   = text.split(" ")
    lines   = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        if len(test) <= chars_per_line:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    canvas_h = MARGIN * 2 + len(lines) * line_h + 20
    canvas   = np.ones((canvas_h, canvas_width, 3), dtype=np.float32)

    # Paper decoration
    lc = np.array([0.78, 0.83, 0.93], dtype=np.float32)
    if paper_style == "lined":
        for y in range(MARGIN + char_h, canvas_h - MARGIN, line_h):
            canvas[y:y+1, MARGIN:canvas_width - MARGIN] = lc
    elif paper_style == "grid":
        for y in range(MARGIN, canvas_h - MARGIN, line_h // 2):
            canvas[y:y+1, MARGIN:canvas_width - MARGIN] = lc
        for x in range(MARGIN, canvas_width - MARGIN, (char_w + CHAR_GAP) // 2):
            canvas[MARGIN:canvas_h - MARGIN, x:x+1] = lc
    elif paper_style == "dotted":
        for y in range(MARGIN + char_h, canvas_h - MARGIN, line_h):
            for x in range(MARGIN, canvas_width - MARGIN, char_w + CHAR_GAP):
                canvas[y, x] = lc

    ink              = np.array(ink_rgb, dtype=np.float32) / 255.0
    baseline_var     = max(0, int(style.get("baseline_variance", 2)) - 1)

    for li, line in enumerate(lines):
        y0 = MARGIN + li * line_h
        x  = MARGIN

        for char in line:
            # Space
            if char == " ":
                x += (char_w + CHAR_GAP) // 2
                continue

            # Overflow guard
            if x + char_w > canvas_width - MARGIN:
                break

            # Get glyph
            if char in glyph_lib:
                glyph = random.choice(glyph_lib[char]).copy()
            else:
                if font_synth is None:
                    font_synth = _load_font_synth()
                glyph = font_synth.synthesize_glyph(char, style_metrics=style, variation=0.12)

            # Resize if needed
            if glyph.shape != (char_h, char_w):
                glyph = cv2.resize(glyph, (char_w, char_h), interpolation=cv2.INTER_AREA)

            # Baseline jitter
            jitter = random.randint(-baseline_var, baseline_var) if baseline_var > 0 else 0
            y_pos  = y0 + jitter
            y_end  = y_pos + char_h
            if y_end > canvas_h or y_pos < 0:
                x += char_w + CHAR_GAP
                continue

            # Extractor uses THRESH_BINARY_INV → 1.0 = ink, 0.0 = paper
            # So alpha IS the glyph value directly — no inversion needed
            alpha = glyph[:, :, np.newaxis]

            roi = canvas[y_pos:y_end, x:x + char_w]
            canvas[y_pos:y_end, x:x + char_w] = roi * (1 - alpha) + ink * alpha

            x += char_w + CHAR_GAP

    return (np.clip(canvas, 0, 1) * 255).astype(np.uint8)


class RenderRequest(BaseModel):
    text:        str
    line_width:  int = 800
    ink_color:   str = "#1a1714"
    paper_style: str = "lined"
    font_size:   int = 24


@router.post("")
async def render_text(req: RenderRequest):
    if not req.text.strip():
        raise HTTPException(400, "Text cannot be empty")
    if len(req.text) > 2000:
        raise HTTPException(400, "Text too long (max 2000 chars)")

    has_glyphs = GLYPH_DIR.exists() and any(GLYPH_DIR.glob("*.png"))
    if not has_glyphs:
        return JSONResponse({"fallback": True, "text": req.text,
                             "reason": "No handwriting uploaded yet — go to the Corpus page first."})

    try:
        ink_rgb = _hex_to_rgb(req.ink_color)
        arr     = _render(req.text, req.line_width, ink_rgb, req.paper_style)
        img     = Image.fromarray(arr)
        buf     = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/png",
                                 headers={"Content-Disposition": "inline; filename=handwriting.png"})
    except Exception as e:
        logger.error(f"Render failed: {e}", exc_info=True)
        return JSONResponse({"fallback": True, "text": req.text, "reason": str(e)})
