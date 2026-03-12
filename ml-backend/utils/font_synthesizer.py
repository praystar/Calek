"""
Font Synthesizer
Generates missing glyphs by:
1. Rendering the character using a handwriting-style font
2. Applying texture/style transfer to match the user's handwriting
3. Adding natural variation (jitter, pressure, baseline offset)

This ensures 100% character coverage even before training.
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import cv2
from pathlib import Path
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)

# Handwriting-style fonts (bundled or system)
# In production: download from Google Fonts or package with the app
FALLBACK_FONTS = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Chalkboard.ttf",  # macOS
    "C:/Windows/Fonts/segoepr.ttf",                       # Windows
]

# Free handwriting fonts to download:
# - Caveat: https://fonts.google.com/specimen/Caveat
# - Homemade Apple: https://fonts.google.com/specimen/Homemade+Apple
# - Handlee: https://fonts.google.com/specimen/Handlee
# - Patrick Hand: https://fonts.google.com/specimen/Patrick+Hand
RECOMMENDED_FONTS = {
    "natural": "Caveat",
    "cursive": "Homemade Apple",
    "print": "Handlee",
    "neat": "Patrick Hand",
}


class FontSynthesizer:
    """
    Synthesizes glyphs for characters missing from the user corpus.
    Applies style transfer to match the handwriting characteristics.
    """

    def __init__(self, glyph_size: int = 64, font_path: Optional[str] = None):
        self.glyph_size = glyph_size
        self.font = self._load_font(font_path)

    def _load_font(self, font_path: Optional[str] = None) -> Optional[ImageFont.FreeTypeFont]:
        """Load font, trying multiple fallbacks."""
        paths = ([font_path] if font_path else []) + FALLBACK_FONTS
        for p in paths:
            if p and Path(p).exists():
                try:
                    font = ImageFont.truetype(p, size=int(self.glyph_size * 0.75))
                    logger.info(f"Loaded font: {p}")
                    return font
                except Exception:
                    pass
        logger.warning("No font found, using default PIL font")
        return ImageFont.load_default()

    def synthesize_glyph(
        self,
        char: str,
        style_metrics: Optional[Dict] = None,
        variation: float = 0.15
    ) -> np.ndarray:
        """
        Render a character with optional style-matching.

        Args:
            char: Single character to render
            style_metrics: Dict with slant, stroke_width, pressure, etc.
            variation: Random variation amount (0-1)

        Returns:
            Normalized grayscale glyph (H × W float32)
        """
        img = self._render_char(char)
        img = self._apply_style(img, style_metrics or {}, variation)
        img = self._normalize_size(img)
        return img

    def synthesize_missing(
        self,
        missing_chars: List[str],
        existing_glyphs: Dict[str, List[np.ndarray]],
        style_metrics: Optional[Dict] = None,
        samples_per_char: int = 3,
    ) -> Dict[str, List[np.ndarray]]:
        """
        Synthesize all missing characters and add to glyph library.

        Args:
            missing_chars: Characters to synthesize
            existing_glyphs: Current glyph library (for style reference)
            style_metrics: Style features from StyleAnalyzer
            samples_per_char: How many samples to generate per character

        Returns:
            Dict of synthesized glyphs keyed by character
        """
        synthesized = {}
        for char in missing_chars:
            glyphs = []
            for i in range(samples_per_char):
                variation = 0.1 + (i * 0.05)  # vary each sample slightly
                g = self.synthesize_glyph(char, style_metrics, variation)
                glyphs.append(g)
            synthesized[char] = glyphs
            logger.debug(f"Synthesized {samples_per_char} samples for '{char}'")

        logger.info(f"Font synthesis complete: {len(synthesized)} characters")
        return synthesized

    def _render_char(self, char: str) -> np.ndarray:
        """Render character to PIL image."""
        size = self.glyph_size * 2  # render at 2x for quality
        img = Image.new("L", (size, size), color=255)
        draw = ImageDraw.Draw(img)

        # Center the character
        try:
            bbox = draw.textbbox((0, 0), char, font=self.font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            x = (size - w) // 2 - bbox[0]
            y = (size - h) // 2 - bbox[1]
        except Exception:
            x, y = size // 4, size // 4

        draw.text((x, y), char, fill=0, font=self.font)
        return np.array(img, dtype=np.float32) / 255.0

    def _apply_style(self, img: np.ndarray, style: Dict, variation: float) -> np.ndarray:
        """Apply handwriting-like transformations."""
        h, w = img.shape

        # 1. Slant
        slant = style.get("slant_angle", 0.0)
        if isinstance(slant, str):
            slant = float(slant.replace("°", ""))
        if abs(slant) > 1:
            M = cv2.getRotationMatrix2D((w // 2, h // 2), -slant, 1.0)
            img = cv2.warpAffine(img, M, (w, h), borderValue=1.0)

        # 2. Add slight random elastic distortion (natural handwriting)
        img = self._elastic_distort(img, strength=variation * 3)

        # 3. Stroke width modulation (simulate pen pressure)
        pressure = style.get("pressure_mean", 0.5)
        if isinstance(pressure, str):
            pressure = {"heavy": 0.8, "medium": 0.5, "light": 0.2}.get(pressure, 0.5)
        img = self._apply_pressure(img, pressure)

        # 4. Mild noise for texture
        noise = np.random.normal(0, variation * 0.04, img.shape).astype(np.float32)
        img = np.clip(img + noise, 0, 1)

        # 5. Slight blur (simulate ink spread)
        img_uint8 = (img * 255).astype(np.uint8)
        blurred = cv2.GaussianBlur(img_uint8, (3, 3), 0.5)
        img = blurred.astype(np.float32) / 255.0

        return img

    def _elastic_distort(self, img: np.ndarray, strength: float = 2.0) -> np.ndarray:
        """Apply smooth random elastic deformation."""
        h, w = img.shape
        dx = np.random.randn(h, w).astype(np.float32) * strength
        dy = np.random.randn(h, w).astype(np.float32) * strength

        # Smooth the displacement fields
        dx = cv2.GaussianBlur(dx, (0, 0), 5)
        dy = cv2.GaussianBlur(dy, (0, 0), 5)

        x, y = np.meshgrid(np.arange(w), np.arange(h))
        map_x = np.clip(x + dx, 0, w - 1).astype(np.float32)
        map_y = np.clip(y + dy, 0, h - 1).astype(np.float32)

        return cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR, borderValue=1.0)

    def _apply_pressure(self, img: np.ndarray, pressure: float) -> np.ndarray:
        """Simulate pen pressure: heavier = darker/thicker ink."""
        binary = (img < 0.5).astype(np.float32)
        if pressure > 0.6:
            # Expand ink (heavier pressure)
            kernel = np.ones((3, 3), np.uint8)
            expanded = cv2.dilate((binary * 255).astype(np.uint8), kernel, iterations=1)
            ink = expanded.astype(np.float32) / 255.0
        elif pressure < 0.35:
            # Thin ink (light pressure)
            kernel = np.ones((2, 2), np.uint8)
            eroded = cv2.erode((binary * 255).astype(np.uint8), kernel, iterations=1)
            ink = eroded.astype(np.float32) / 255.0
        else:
            ink = binary

        return 1.0 - ink

    def _normalize_size(self, img: np.ndarray) -> np.ndarray:
        """Resize to target glyph size."""
        resized = cv2.resize(img, (self.glyph_size, self.glyph_size), interpolation=cv2.INTER_AREA)
        return resized.astype(np.float32)
