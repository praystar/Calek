"""
Render route
Text → handwriting image using the user's REAL extracted glyph PNGs.
Falls back to font synthesis for any missing characters.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from pathlib import Path
from typing import Optional
import io, logging, json, random
import numpy as np
import cv2
from PIL import Image, ImageDraw

router = APIRouter()
logger = logging.getLogger(__name__)

GLYPH_DIR   = Path("data/user_glyphs")
STYLE_FILE  = Path("data/user_glyphs/style.json")
GLYPH_SIZE  = 64   # px — must match CharacterExtractor.glyph_size
LINE_GAP    = 16   # px between lines
MARGIN      = 36   # px left/top/bottom margin


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
    """Load all saved glyph PNGs into a dict keyed by character."""
    library: dict = {}
    for f in GLYPH_DIR.glob("*.png"):
        try:
            codepoint = int(f.stem.split("_")[0])
            char = chr(codepoint)
            img = np.array(Image.open(f).convert("L"), dtype=np.float32) / 255.0
            if char not in library:
                library[char] = []
            library[char].append(img)
        except Exception:
            pass
    return library


def _load_style() -> dict:
    if STYLE_FILE.exists():
        return json.loads(STYLE_FILE.read_text())
    return {}


def _render_text_to_array(
    text: str,
    canvas_width: int,
    ink_rgb: tuple,
    paper_style: str,
    font_size: int,
) -> np.ndarray:
    """
    Composite real glyph images into a full handwriting page.
    Each character image is pasted at the right position with ink colouring.
    Missing chars are synthesized on-the-fly matching the user's style.
    """
    glyph_lib  = _load_glyph_library()
    style      = _load_style()
    font_synth = None  # lazy init only if needed

    char_w     = GLYPH_SIZE
    char_h     = GLYPH_SIZE
    line_h     = char_h + LINE_GAP
    chars_per_line = max(1, (canvas_width - 2 * MARGIN) // char_w)

    # Word-wrap
    words  = text.split(" ")
    lines: list[str] = []
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

    canvas_h = max(MARGIN * 2 + len(lines) * line_h + 40, 200)

    # White background
    canvas = np.ones((canvas_h, canvas_width, 3), dtype=np.float32)

    # Paper lines / grid
    line_col = np.array([0.78, 0.83, 0.93], dtype=np.float32)  # light blue
    if paper_style == "lined":
        for y in range(MARGIN + char_h, canvas_h - MARGIN, line_h):
            canvas[y:y+1, MARGIN:canvas_width - MARGIN] = line_col
    elif paper_style == "grid":
        for y in range(MARGIN, canvas_h - MARGIN, line_h // 2):
            canvas[y:y+1, MARGIN:canvas_width - MARGIN] = line_col
        for x in range(MARGIN, canvas_width - MARGIN, char_w // 2):
            canvas[MARGIN:canvas_h - MARGIN, x:x+1] = line_col
    elif paper_style == "dotted":
        for y in range(MARGIN + char_h, canvas_h - MARGIN, line_h):
            for x in range(MARGIN, canvas_width - MARGIN, char_w // 2):
                canvas[y, x] = line_col

    # Slant offset per char (simulate natural writing angle)
    slant = style.get("slant_angle", 0.0)

    ink = np.array(ink_rgb, dtype=np.float32) / 255.0

    for line_idx, line in enumerate(lines):
        y0 = MARGIN + line_idx * line_h
        # Small random baseline jitter per line
        baseline_jitter = int(style.get("baseline_variance", 2.5))

        x = MARGIN
        for char in line:
            if x + char_w > canvas_width - MARGIN:
                break

            # Get glyph image
            if char in glyph_lib:
                # Pick randomly from available samples for natural variation
                glyph_gray = random.choice(glyph_lib[char])
            elif char == " ":
                x += char_w // 2
                continue
            else:
                # Synthesize missing char on the fly
                if font_synth is None:
                    font_synth = _load_font_synth()
                glyph_gray = font_synth.synthesize_glyph(char, style_metrics=style, variation=0.1)

            if glyph_gray.shape != (char_h, char_w):
                glyph_gray = cv2.resize(glyph_gray, (char_w, char_h), interpolation=cv2.INTER_AREA)

            # Vertical jitter for natural baseline variation
            jitter = random.randint(-max(0, baseline_jitter - 2), max(0, baseline_jitter - 2))
            y_pos = y0 + jitter
            y_end = y_pos + char_h
            if y_end > canvas_h:
                break

            # Ink mask: glyph_gray is 0=ink, 1=paper (inverted)
            alpha = np.clip(1.0 - glyph_gray, 0, 1)[:, :, np.newaxis]

            # Blend ink onto canvas
            roi = canvas[y_pos:y_end, x:x + char_w]
            canvas[y_pos:y_end, x:x + char_w] = roi * (1 - alpha) + ink * alpha

            x += char_w + int(style.get("letter_spacing_mean", 4))

    # Convert to uint8
    return (np.clip(canvas, 0, 1) * 255).astype(np.uint8)


# ── Request model ──────────────────────────────────────────────────────────────

class RenderRequest(BaseModel):
    text:        str
    line_width:  int    = 800
    ink_color:   str    = "#1a1714"
    paper_style: str    = "lined"
    font_size:   int    = 24


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("")
async def render_text(req: RenderRequest):
    """Render text as a handwriting PNG using the user's real extracted glyphs."""
    if not req.text.strip():
        raise HTTPException(400, "Text cannot be empty")
    if len(req.text) > 2000:
        raise HTTPException(400, "Text too long (max 2000 chars)")

    # Check glyphs exist
    if not GLYPH_DIR.exists() or not any(GLYPH_DIR.glob("*.png")):
        # No real glyphs yet — return JSON so frontend shows CSS fallback
        return JSONResponse({"text": req.text, "fallback": True,
                             "reason": "No handwriting uploaded yet. Go to the Corpus page first."})

    try:
        ink_rgb  = _hex_to_rgb(req.ink_color)
        img_arr  = _render_text_to_array(
            text         = req.text,
            canvas_width = req.line_width,
            ink_rgb      = ink_rgb,
            paper_style  = req.paper_style,
            font_size    = req.font_size,
        )

        img = Image.fromarray(img_arr)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)

        return StreamingResponse(
            buf,
            media_type="image/png",
            headers={"Content-Disposition": "inline; filename=handwriting.png"}
        )

    except Exception as e:
        logger.error(f"Render failed: {e}", exc_info=True)
        return JSONResponse({"text": req.text, "fallback": True, "reason": str(e)})
