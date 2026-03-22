"""
Character Extractor
Segments handwriting images into individual character glyphs using:
1. Connected component analysis
2. Projection-based line/word segmentation
3. Character-level bounding box extraction
"""

import cv2
import numpy as np
from PIL import Image
from pathlib import Path
import logging
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)


@dataclass
class Glyph:
    char: str
    image: np.ndarray          # Normalized grayscale glyph image
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    confidence: float
    source_file: str


class CharacterExtractor:
    """
    Extracts character glyphs from handwriting images.

    Pipeline:
        raw image → binarize → deskew → segment lines →
        segment words → segment chars → normalize → OCR label
    """

    def __init__(self, glyph_size: int = 64):
        self.glyph_size = glyph_size
        self._init_ocr()

    def _init_ocr(self):
        """Initialize EasyOCR for character labeling."""
        try:
            import easyocr
            self.reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            logger.info("EasyOCR initialized")
        except Exception as e:
            logger.warning(f"EasyOCR not available: {e}. Using Tesseract fallback.")
            self.reader = None

    def extract_from_image(self, image_path: str) -> List[Glyph]:
        """
        Extract all character glyphs from a handwriting image.

        Args:
            image_path: Path to the handwriting image

        Returns:
            List of Glyph objects with images and labels
        """
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Cannot read image: {image_path}")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        binary = self._binarize(gray)
        deskewed = self._deskew(binary)
        lines = self._segment_lines(deskewed)

        glyphs = []
        for line_img in lines:
            words = self._segment_words(line_img)
            for word_img in words:
                chars = self._segment_characters(word_img)
                labeled = self._label_characters(chars, word_img, image_path)
                glyphs.extend(labeled)

        logger.info(f"Extracted {len(glyphs)} glyphs from {image_path}")
        return glyphs

    def _binarize(self, gray: np.ndarray) -> np.ndarray:
        """Adaptive thresholding + noise removal."""
        denoised = cv2.fastNlMeansDenoising(gray, h=10)
        binary = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 21, 10
        )
        kernel = np.ones((2, 2), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        return binary

    def _deskew(self, binary: np.ndarray) -> np.ndarray:
        """Correct image skew using Hough line transform."""
        coords = np.column_stack(np.where(binary > 0))
        if len(coords) == 0:
            return binary

        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        if abs(angle) < 0.5:
            return binary

        h, w = binary.shape
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(binary, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        return rotated

    def _segment_lines(self, binary: np.ndarray, min_gap: int = 10) -> List[np.ndarray]:
        """Horizontal projection profile for line segmentation."""
        h_proj = np.sum(binary, axis=1)
        lines = []
        in_line = False
        start = 0

        for i, val in enumerate(h_proj):
            if val > 5 and not in_line:
                in_line = True
                start = max(0, i - 3)
            elif val <= 5 and in_line:
                in_line = False
                end = min(binary.shape[0], i + 3)
                line = binary[start:end, :]
                if line.shape[0] > 10:
                    lines.append(line)

        if in_line:
            lines.append(binary[start:, :])

        return lines

    def _segment_words(self, line: np.ndarray, min_gap: int = 15) -> List[np.ndarray]:
        """Vertical projection for word segmentation."""
        v_proj = np.sum(line, axis=0)
        words = []
        in_word = False
        start = 0
        gap_count = 0

        for i, val in enumerate(v_proj):
            if val > 0 and not in_word:
                in_word = True
                start = max(0, i - 2)
                gap_count = 0
            elif val == 0 and in_word:
                gap_count += 1
                if gap_count >= min_gap:
                    in_word = False
                    word = line[:, start:i]
                    if word.shape[1] > 5:
                        words.append(word)
            elif val > 0 and in_word:
                gap_count = 0

        if in_word:
            words.append(line[:, start:])

        return words if words else [line]

    def _segment_characters(self, word: np.ndarray) -> List[Tuple[np.ndarray, Tuple]]:
        """Segment characters, merging nearby strokes before splitting."""
        # Dilate horizontally to merge disconnected strokes (e, H, i dots etc.)
        merged = self._merge_nearby_components(word, gap=6)

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(merged, connectivity=8)
        chars = []

        components = sorted(
            [(stats[i], i) for i in range(1, num_labels)],
            key=lambda x: x[0][cv2.CC_STAT_LEFT]
        )

        word_h = word.shape[0]
        word_w = word.shape[1]
        for stat, label_id in components:
            x = stat[cv2.CC_STAT_LEFT]
            y = stat[cv2.CC_STAT_TOP]
            w = stat[cv2.CC_STAT_WIDTH]
            h = stat[cv2.CC_STAT_HEIGHT]
            area = stat[cv2.CC_STAT_AREA]

            if area < 30 or h < word_h * 0.2 or w < 3:
                continue
            if w > word_w * 0.65 or h > word_h * 1.2:
                continue
            aspect = w / max(h, 1)
            if aspect > 5.0 or aspect < 0.08:
                continue

            # Crop from ORIGINAL word (not dilated) for clean glyph pixels
            char_img = word[y:y+h, x:x+w]
            chars.append((char_img, (x, y, w, h)))

        return chars

    def _label_characters(
        self,
        chars: List[Tuple[np.ndarray, Tuple]],
        word_img: np.ndarray,
        source: str
    ) -> List[Glyph]:
        """Use OCR to label extracted character regions."""
        glyphs = []

        # Get word-level OCR text for alignment
        word_text = self._ocr_word(word_img)

        for i, (char_img, bbox) in enumerate(chars):
            normalized = self._normalize_glyph(char_img)
            # Try to match char to OCR word text
            char_label = word_text[i] if i < len(word_text) else "?"
            conf = 0.9 if i < len(word_text) else 0.3

            glyphs.append(Glyph(
                char=char_label,
                image=normalized,
                bbox=bbox,
                confidence=conf,
                source_file=source
            ))

        return glyphs

    def _ocr_word(self, word_img: np.ndarray) -> str:
        """OCR a single word image."""
        try:
            if self.reader:
                results = self.reader.readtext(word_img, detail=0)
                return "".join(results).strip()
            else:
                import pytesseract
                pil = Image.fromarray(word_img)
                text = pytesseract.image_to_string(pil, config="--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!?")
                return text.strip()
        except Exception as e:
            logger.warning(f"OCR failed: {e}")
            return ""

    def _normalize_glyph(self, glyph: np.ndarray) -> np.ndarray:
        """Normalize glyph to fixed size. ink=1.0 (bright), paper=0.0 (dark)."""
        padded  = cv2.copyMakeBorder(glyph, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=0)
        resized = cv2.resize(padded, (self.glyph_size, self.glyph_size), interpolation=cv2.INTER_AREA)
        norm    = resized.astype(np.float32) / 255.0
        # Use border pixels to detect inversion — border is pure padding (value=0=paper).
        # If border is bright, image is inverted.
        border = np.concatenate([norm[0,:], norm[-1,:], norm[:,0], norm[:,-1]])
        if np.mean(border) > 0.15:
            norm = 1.0 - norm
        return np.clip(norm, 0.0, 1.0)

    def _merge_nearby_components(self, word: np.ndarray, gap: int = 6) -> np.ndarray:
        """Dilate horizontally to merge disconnected strokes of the same letter."""
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (gap, 1))
        return cv2.dilate(word, kernel, iterations=1)

    def build_glyph_library(self, glyphs: List[Glyph]) -> Dict[str, List[np.ndarray]]:
        """
        Organize glyphs into a library keyed by character.
        Multiple samples per character are kept for style averaging.
        """
        library = {}
        for g in glyphs:
            if g.confidence > 0.5 and g.char.strip():
                if g.char not in library:
                    library[g.char] = []
                library[g.char].append(g.image)

        logger.info(f"Glyph library: {len(library)} unique characters, "
                    f"{sum(len(v) for v in library.values())} total samples")
        return library

    def get_coverage_report(self, library: Dict) -> Dict:
        """Report which characters are present/missing."""
        all_chars = list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,!?'\"-")
        present = [c for c in all_chars if c in library]
        missing = [c for c in all_chars if c not in library]
        return {
            "present": present,
            "missing": missing,
            "coverage_pct": round(len(present) / len(all_chars) * 100, 1),
            "samples_per_char": {c: len(library[c]) for c in present}
        }
