"""Corpus API routes — upload, analyze, and synthesize handwriting."""

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import tempfile, os, shutil, logging
from pathlib import Path

router = APIRouter()
logger = logging.getLogger(__name__)

# Lazy-load heavy ML modules
_extractor = None
_style_analyzer = None
_font_synth = None
_model = None
_glyph_library = {}


def get_extractor():
    global _extractor
    if _extractor is None:
        from utils.character_extractor import CharacterExtractor
        _extractor = CharacterExtractor()
    return _extractor


def get_style_analyzer():
    global _style_analyzer
    if _style_analyzer is None:
        from utils.style_analyzer import StyleAnalyzer
        _style_analyzer = StyleAnalyzer()
    return _style_analyzer


def get_font_synth():
    global _font_synth
    if _font_synth is None:
        from utils.font_synthesizer import FontSynthesizer
        _font_synth = FontSynthesizer()
    return _font_synth


def get_model():
    global _model
    if _model is None:
        from models.handwriting_model import HandwritingSynthesizer
        _model = HandwritingSynthesizer()
    return _model


@router.post("/analyze")
async def analyze_corpus(images: List[UploadFile] = File(...)):
    """
    Analyze uploaded handwriting images:
    - Extract individual glyphs
    - Compute style metrics
    - Report character coverage
    """
    global _glyph_library
    tmpdir = tempfile.mkdtemp()

    try:
        saved_paths = []
        for img in images:
            if not img.content_type.startswith("image/"):
                raise HTTPException(400, f"File {img.filename} is not an image")
            dest = os.path.join(tmpdir, img.filename or "image.png")
            with open(dest, "wb") as f:
                shutil.copyfileobj(img.file, f)
            saved_paths.append(dest)

        # Extract glyphs
        extractor = get_extractor()
        all_glyphs = []
        for path in saved_paths:
            try:
                glyphs = extractor.extract_from_image(path)
                all_glyphs.extend(glyphs)
            except Exception as e:
                logger.warning(f"Failed to extract from {path}: {e}")

        _glyph_library = extractor.build_glyph_library(all_glyphs)

        # Style analysis
        style_analyzer = get_style_analyzer()
        style_vec = style_analyzer.analyze_multiple(saved_paths)
        style_dict = style_vec.to_dict()

        # Coverage
        coverage = extractor.get_coverage_report(_glyph_library)

        # Encode style into model
        model = get_model()
        model.encode_style(_glyph_library)

        return JSONResponse({
            "total_images": len(saved_paths),
            "total_glyphs_extracted": len(all_glyphs),
            "characters_found": len(coverage["present"]),
            "characters_present": coverage["present"],
            "characters_missing": coverage["missing"],
            "coverage_pct": coverage["coverage_pct"],
            "style_metrics": style_dict,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Corpus analysis failed: {e}")
        raise HTTPException(500, str(e))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


class SynthesizeRequest(BaseModel):
    missing_chars: List[str]
    style_metrics: Optional[dict] = None


@router.post("/synthesize")
async def synthesize_missing(req: SynthesizeRequest):
    """Synthesize missing glyphs using font + style transfer."""
    try:
        font_synth = get_font_synth()
        synthesized = font_synth.synthesize_missing(
            missing_chars=req.missing_chars,
            existing_glyphs=_glyph_library,
            style_metrics=req.style_metrics,
        )

        # Add to global library
        _glyph_library.update(synthesized)

        # Re-encode style
        model = get_model()
        model.encode_style(_glyph_library)

        return {"synthesized": list(synthesized.keys()), "total_library_size": len(_glyph_library)}
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        raise HTTPException(500, str(e))


@router.post("/match-style")
async def match_style(images: List[UploadFile] = File(...)):
    """
    Upload 1–3 handwriting photos → returns the closest preset style ID
    by comparing extracted style metrics against all preset style vectors.
    """
    import json, math
    tmpdir = tempfile.mkdtemp()
    try:
        saved_paths = []
        for img in images:
            dest = os.path.join(tmpdir, img.filename or "img.png")
            with open(dest, "wb") as f:
                shutil.copyfileobj(img.file, f)
            saved_paths.append(dest)

        # Extract style from uploaded images
        style_analyzer = get_style_analyzer()
        style_vec = style_analyzer.analyze_multiple(saved_paths)

        # Load preset library
        preset_path = Path(__file__).parent.parent / "data" / "preset_styles" / "styles.json"
        with open(preset_path) as f:
            presets = json.load(f)

        # Euclidean distance in style space (normalized)
        def style_distance(preset):
            d = 0
            weights = {
                "slant_angle": 0.30,
                "stroke_width_mean": 0.20,
                "letter_spacing_mean": 0.15,
                "baseline_variance": 0.10,
                "pressure_mean": 0.15,
                "loop_density": 0.10,
            }
            ranges = {
                "slant_angle": 20, "stroke_width_mean": 3,
                "letter_spacing_mean": 15, "baseline_variance": 8,
                "pressure_mean": 1, "loop_density": 1,
            }
            for key, w in weights.items():
                user_val = getattr(style_vec, key, 0)
                preset_val = preset.get(key, 0)
                r = ranges.get(key, 1)
                d += w * ((user_val - preset_val) / r) ** 2
            return math.sqrt(d)

        best_id = min(presets, key=lambda k: style_distance(presets[k]))
        best = presets[best_id]
        dist = style_distance(best)
        confidence = max(40, min(99, int(100 - dist * 120)))

        # Load this preset's style into the model
        model = get_model()
        from utils.style_analyzer import StyleVector
        sv = StyleVector(
            slant_angle=best["slant_angle"],
            stroke_width_mean=best["stroke_width_mean"],
            stroke_width_std=best["stroke_width_std"],
            letter_spacing_mean=best["letter_spacing_mean"],
            baseline_variance=best["baseline_variance"],
            pressure_mean=best["pressure_mean"],
            pressure_std=best["pressure_std"],
            aspect_ratio_mean=best["aspect_ratio_mean"],
            loop_density=best["loop_density"],
        )

        return JSONResponse({
            "matched_id": best_id,
            "label": best["label"],
            "confidence": confidence,
            "slant": f"{best['slant_angle']}°",
            "pressure": sv.to_dict()["pen_pressure"],
            "spacing": sv.to_dict()["letter_spacing"],
            "preview": "Hello World",
        })
    except Exception as e:
        logger.error(f"Style matching failed: {e}")
        raise HTTPException(500, str(e))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@router.post("/train")
async def train_model(epochs: int = 50):
    """Fine-tune the synthesis model on the current glyph library."""
    if not _glyph_library:
        raise HTTPException(400, "No glyph library loaded. Run /corpus/analyze first.")
    try:
        model = get_model()
        model.train_on_corpus(_glyph_library, epochs=epochs)
        return {"status": "training_complete", "epochs": epochs}
    except Exception as e:
        raise HTTPException(500, str(e))
