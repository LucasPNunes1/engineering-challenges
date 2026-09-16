"""Convert OCR coordinates (300 dpi pixels) to challenge submission coordinates."""

from __future__ import annotations


OCR_DPI = 300
POINTS_PER_INCH = 72


def normalize_ocr_bbox(bbox_px: list[float], page_width_pt: float, page_height_pt: float) -> list[float]:
    """Return a [0, 1] bbox from the OCR's 300-dpi pixel coordinate system."""
    if len(bbox_px) != 4:
        raise ValueError("bbox must contain exactly four values")
    scale = OCR_DPI / POINTS_PER_INCH
    width_px = page_width_pt * scale
    height_px = page_height_pt * scale
    normalized = [
        bbox_px[0] / width_px,
        bbox_px[1] / height_px,
        bbox_px[2] / width_px,
        bbox_px[3] / height_px,
    ]
    if any(value < 0 or value > 1 for value in normalized):
        raise ValueError(f"OCR bbox falls outside PDF page after normalization: {normalized}")
    return normalized
