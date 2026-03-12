"""
Style Analyzer
Extracts quantitative style features from handwriting samples:
 - Slant angle
 - Stroke width distribution
 - Letter spacing
 - Baseline consistency
 - Pen pressure (contrast mapping)
 - Writing rhythm (inter-character timing proxy)
"""

import cv2
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class StyleVector:
    """Compact representation of handwriting style."""
    slant_angle: float          # degrees, negative = left-leaning
    stroke_width_mean: float    # px at 300dpi
    stroke_width_std: float
    letter_spacing_mean: float
    baseline_variance: float
    pressure_mean: float        # 0-1 proxy from ink density
    pressure_std: float
    aspect_ratio_mean: float    # width/height of glyphs
    loop_density: float         # closed loops frequency

    def to_dict(self) -> Dict:
        return {
            "avg_slant": f"{self.slant_angle:.1f}°",
            "stroke_width": f"{self.stroke_width_mean:.1f}px",
            "letter_spacing": self._classify_spacing(),
            "baseline_variance": self._classify_baseline(),
            "pen_pressure": self._classify_pressure(),
        }

    def _classify_spacing(self) -> str:
        if self.letter_spacing_mean < 8: return "tight"
        if self.letter_spacing_mean < 15: return "normal"
        return "wide"

    def _classify_baseline(self) -> str:
        if self.baseline_variance < 3: return "very low"
        if self.baseline_variance < 6: return "low"
        if self.baseline_variance < 12: return "medium"
        return "high"

    def _classify_pressure(self) -> str:
        if self.pressure_mean > 0.7: return "heavy"
        if self.pressure_mean > 0.4: return "medium"
        return "light"


class StyleAnalyzer:
    """
    Analyzes handwriting style from binary/grayscale images.
    Produces a StyleVector used for conditioning synthesis.
    """

    def analyze_image(self, image_path: str) -> StyleVector:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"Cannot read: {image_path}")

        _, binary = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        slant = self._estimate_slant(binary)
        stroke_mean, stroke_std = self._estimate_stroke_width(binary)
        spacing = self._estimate_letter_spacing(binary)
        baseline_var = self._estimate_baseline_variance(binary)
        pressure_mean, pressure_std = self._estimate_pressure(img)
        aspect = self._estimate_aspect_ratio(binary)
        loops = self._estimate_loop_density(binary)

        return StyleVector(
            slant_angle=slant,
            stroke_width_mean=stroke_mean,
            stroke_width_std=stroke_std,
            letter_spacing_mean=spacing,
            baseline_variance=baseline_var,
            pressure_mean=pressure_mean,
            pressure_std=pressure_std,
            aspect_ratio_mean=aspect,
            loop_density=loops,
        )

    def analyze_multiple(self, image_paths: List[str]) -> StyleVector:
        """Average style over multiple images."""
        vectors = []
        for p in image_paths:
            try:
                vectors.append(self.analyze_image(p))
            except Exception as e:
                logger.warning(f"Failed to analyze {p}: {e}")

        if not vectors:
            raise ValueError("No images could be analyzed")

        return StyleVector(
            slant_angle=np.mean([v.slant_angle for v in vectors]),
            stroke_width_mean=np.mean([v.stroke_width_mean for v in vectors]),
            stroke_width_std=np.mean([v.stroke_width_std for v in vectors]),
            letter_spacing_mean=np.mean([v.letter_spacing_mean for v in vectors]),
            baseline_variance=np.mean([v.baseline_variance for v in vectors]),
            pressure_mean=np.mean([v.pressure_mean for v in vectors]),
            pressure_std=np.mean([v.pressure_std for v in vectors]),
            aspect_ratio_mean=np.mean([v.aspect_ratio_mean for v in vectors]),
            loop_density=np.mean([v.loop_density for v in vectors]),
        )

    def _estimate_slant(self, binary: np.ndarray) -> float:
        """Estimate slant using vertical projection of ink strokes."""
        # Use Hough line transform on skeleton
        kernel = np.ones((3, 1), np.uint8)
        eroded = cv2.erode(binary, kernel, iterations=1)
        lines = cv2.HoughLines(eroded, 1, np.pi / 180, threshold=50)

        if lines is None:
            return 0.0

        angles = []
        for line in lines[:20]:
            theta = line[0][1]
            angle = np.degrees(theta) - 90
            if abs(angle) < 45:
                angles.append(angle)

        return float(np.median(angles)) if angles else 0.0

    def _estimate_stroke_width(self, binary: np.ndarray) -> tuple:
        """Distance transform gives stroke width at each ink pixel."""
        dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
        ink_widths = dist[binary > 0] * 2  # radius → diameter
        if len(ink_widths) == 0:
            return 2.0, 0.5
        return float(np.mean(ink_widths)), float(np.std(ink_widths))

    def _estimate_letter_spacing(self, binary: np.ndarray) -> float:
        """Measure gaps between connected components."""
        num_labels, _, stats, _ = cv2.connectedComponentsWithStats(binary)
        if num_labels < 3:
            return 10.0

        sorted_x = sorted(stats[1:, cv2.CC_STAT_LEFT])
        sorted_w = sorted(stats[1:, cv2.CC_STAT_WIDTH])

        gaps = []
        for i in range(len(sorted_x) - 1):
            gap = sorted_x[i + 1] - (sorted_x[i] + sorted_w[i])
            if 0 < gap < 100:
                gaps.append(gap)

        return float(np.mean(gaps)) if gaps else 10.0

    def _estimate_baseline_variance(self, binary: np.ndarray) -> float:
        """Variance of character baseline positions."""
        num_labels, _, stats, _ = cv2.connectedComponentsWithStats(binary)
        if num_labels < 3:
            return 5.0

        baselines = stats[1:, cv2.CC_STAT_TOP] + stats[1:, cv2.CC_STAT_HEIGHT]
        return float(np.std(baselines))

    def _estimate_pressure(self, gray: np.ndarray) -> tuple:
        """Ink density as proxy for pen pressure."""
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ink_pixels = gray[binary > 0]

        if len(ink_pixels) == 0:
            return 0.5, 0.1

        darkness = 1.0 - ink_pixels.astype(float) / 255.0
        return float(np.mean(darkness)), float(np.std(darkness))

    def _estimate_aspect_ratio(self, binary: np.ndarray) -> float:
        """Average width/height ratio of character bounding boxes."""
        num_labels, _, stats, _ = cv2.connectedComponentsWithStats(binary)
        if num_labels < 2:
            return 0.6

        ratios = []
        for i in range(1, num_labels):
            w = stats[i, cv2.CC_STAT_WIDTH]
            h = stats[i, cv2.CC_STAT_HEIGHT]
            if h > 5 and w > 2:
                ratios.append(w / h)

        return float(np.mean(ratios)) if ratios else 0.6

    def _estimate_loop_density(self, binary: np.ndarray) -> float:
        """Estimate frequency of closed loops (e.g., o, a, e, d)."""
        # Find contours and check for enclosed areas
        contours, hierarchy = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if hierarchy is None or len(hierarchy) == 0:
            return 0.0

        h = hierarchy[0]
        total = len(contours)
        inner = np.sum(h[:, 3] != -1)  # has parent = inner loop
        return float(inner / total) if total > 0 else 0.0
