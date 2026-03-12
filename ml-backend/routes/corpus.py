"""
Corpus routes
Upload 1–3 photos of your handwriting → extract real character glyphs →
save to disk → use those actual images when rendering text.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import tempfile, os, shutil, logging, json
from pathlib import Path
import numpy as np
import cv2
from PIL import Image

router = APIRouter()
logger = logging.getLogger(__name__)

GLYPH_DIR = Path("data/user_glyphs")
GLYPH_DIR.mkdir(parents=True, exist_ok=True)
STYLE_FILE = Path("data/user_glyphs/style.json")

_style_metrics: dict = {}


def _load_style_analyzer():
    from utils.style_analyzer import StyleAnalyzer
    return StyleAnalyzer()

def _load_extractor():
    from utils.character_extractor import CharacterExtractor
    return CharacterExtractor()

def _load_font_synth():
    from utils.font_synthesizer import FontSynthesizer
    return FontSynthesizer()


def _save_glyph_image(char: str, img_array: np.ndarray, index: int) -> Path:
    safe = ord(char)
    path = GLYPH_DIR / f"{safe}_{index}.png"
    pil = Image.fromarray((img_array * 255).astype(np.uint8))
    pil.save(path)
    return path


def _list_saved_chars() -> List[str]:
    chars = set()
    for f in GLYPH_DIR.glob("*.png"):
        try:
            codepoint = int(f.stem.split("_")[0])
            chars.add(chr(codepoint))
        except Exception:
            pass
    return sorted(chars)


@router.post("/analyze")
async def analyze_corpus(images: List[UploadFile] = File(...)):
    """
    Upload 1-3 handwriting photos.
    Extracts every legible character as a real glyph PNG saved to disk.
    """
    global _style_metrics
    tmpdir = tempfile.mkdtemp()

    try:
        saved_paths = []
        for img in images:
            if not img.content_type.startswith("image/"):
                raise HTTPException(400, f"{img.filename} is not an image")
            dest = os.path.join(tmpdir, img.filename or "image.png")
            with open(dest, "wb") as f:
                shutil.copyfileobj(img.file, f)
            saved_paths.append(dest)

        extractor = _load_extractor()
        all_glyphs = []
        for path in saved_paths:
            try:
                glyphs = extractor.extract_from_image(path)
                all_glyphs.extend(glyphs)
                logger.info(f"Extracted {len(glyphs)} glyphs from {path}")
            except Exception as e:
                logger.warning(f"Extraction failed for {path}: {e}")

        if not all_glyphs:
            raise HTTPException(422, "Could not extract any characters. Try a clearer photo with dark ink on white paper.")

        # Clear old glyphs and save new real ones
        for old in GLYPH_DIR.glob("*.png"):
            old.unlink()

        glyph_counts: dict = {}
        for g in all_glyphs:
            if not g.char.strip() or g.confidence < 0.4:
                continue
            idx = glyph_counts.get(g.char, 0)
            _save_glyph_image(g.char, g.image, idx)
            glyph_counts[g.char] = idx + 1

        if not glyph_counts:
            raise HTTPException(422, "Characters found but could not be labeled. Make sure writing is clear and well-lit.")

        # Save style metrics
        analyzer = _load_style_analyzer()
        style_vec = analyzer.analyze_multiple(saved_paths)
        _style_metrics = style_vec.to_dict()
        STYLE_FILE.write_text(json.dumps({
            "slant_angle":         style_vec.slant_angle,
            "stroke_width_mean":   style_vec.stroke_width_mean,
            "stroke_width_std":    style_vec.stroke_width_std,
            "letter_spacing_mean": style_vec.letter_spacing_mean,
            "baseline_variance":   style_vec.baseline_variance,
            "pressure_mean":       style_vec.pressure_mean,
            "pressure_std":        style_vec.pressure_std,
            "aspect_ratio_mean":   style_vec.aspect_ratio_mean,
            "loop_density":        style_vec.loop_density,
        }))

        all_chars = list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,!?'\"")
        present = [c for c in all_chars if c in glyph_counts]
        missing = [c for c in all_chars if c not in glyph_counts]

        return JSONResponse({
            "total_images":           len(saved_paths),
            "total_glyphs_extracted": len(all_glyphs),
            "characters_found":       len(present),
            "characters_present":     present,
            "characters_missing":     missing,
            "coverage_pct":           round(len(present) / len(all_chars) * 100, 1),
            "samples_per_char":       glyph_counts,
            "style_metrics":          _style_metrics,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Corpus analysis failed: {e}", exc_info=True)
        raise HTTPException(500, str(e))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


class SynthesizeRequest(BaseModel):
    missing_chars: List[str]


@router.post("/synthesize")
async def synthesize_missing(req: SynthesizeRequest):
    """
    Synthesize missing chars using font + user's extracted style metrics.
    Saved alongside real glyphs so /render uses them transparently.
    """
    if not req.missing_chars:
        return {"synthesized": [], "message": "Nothing to synthesize"}

    style = json.loads(STYLE_FILE.read_text()) if STYLE_FILE.exists() else None

    font_synth = _load_font_synth()
    synthesized = font_synth.synthesize_missing(
        missing_chars=req.missing_chars,
        existing_glyphs={},
        style_metrics=style,
        samples_per_char=2,
    )
    for char, imgs in synthesized.items():
        for i, img in enumerate(imgs):
            _save_glyph_image(char, img, i)

    return {
        "synthesized": list(synthesized.keys()),
        "total_glyphs_on_disk": len(list(GLYPH_DIR.glob("*.png"))),
    }


@router.get("/status")
async def corpus_status():
    chars = _list_saved_chars()
    return {"ready": len(chars) > 0, "total_chars": len(chars), "chars": chars, "has_style": STYLE_FILE.exists()}


class SetPresetRequest(BaseModel):
    style_id: str


@router.post("/set-preset")
async def set_preset(req: SetPresetRequest):
    """
    Load a preset IAM style vector into the active style file
    so /render uses those metrics for synthesizing missing chars.
    """
    preset_path = Path(__file__).parent.parent / "data" / "preset_styles" / "styles.json"
    if not preset_path.exists():
        raise HTTPException(404, "Preset styles file not found")

    presets = json.loads(preset_path.read_text())
    if req.style_id not in presets:
        raise HTTPException(404, f"Unknown style id: {req.style_id}")

    # Clear any real user glyphs so renderer falls back to font synthesis
    for old in GLYPH_DIR.glob("*.png"):
        old.unlink()

    # Write preset metrics as the active style
    preset = presets[req.style_id]
    STYLE_FILE.write_text(json.dumps({k: v for k, v in preset.items()
                                      if k not in ("label", "iam_writer_id")}))

    return {"ok": True, "style_id": req.style_id, "label": preset["label"]}
