"""
Image processing utilities for nutrition label detection and preprocessing.
"""

from __future__ import annotations

import base64

import cv2
import numpy as np

from .ocr import get_ocr_engine

MAX_IMAGE_DIM = 768


# ---------------------------------------------------------------------------
# Label detection
# ---------------------------------------------------------------------------


def detect_label_ocr(image: np.ndarray) -> np.ndarray | None:
    """
    Locate the nutrition / ingredients region using OCR anchor text.

    Searches for 'Ingredient' first (higher priority), then 'Nutrition Facts'.
    Returns a crop that extends from the anchor downward to cover the full
    label text block.

    Args:
        image (np.ndarray): BGR image array loaded via OpenCV.

    Returns:
        np.ndarray | None: Cropped label region, or None if no anchor found.
    """
    ocr = get_ocr_engine()
    results = ocr.ocr(image)

    anchor_box = None
    anchor_priority: str | None = None

    for line in results[0]:
        text = line[1][0].lower()

        if "ingredient" in text and anchor_priority != "ingredients":
            anchor_box = line[0]
            anchor_priority = "ingredients"

        elif "nutrition" in text and "fact" in text and anchor_priority is None:
            anchor_box = line[0]
            anchor_priority = "nutrition"

    if anchor_box is None:
        return None

    xs = [p[0] for p in anchor_box]
    ys = [p[1] for p in anchor_box]

    x1, y1 = int(min(xs)), int(min(ys))
    x2, y2 = int(max(xs)), int(max(ys))

    h, w = image.shape[:2]

    margin_top = 80
    margin_side = 300
    margin_bottom = int(h * 0.85)

    x1 = max(0, x1 - margin_side)
    y1 = max(0, y1 - margin_top)
    x2 = min(w, x2 + margin_side)
    y2 = min(h, y2 + margin_bottom)

    return image[y1:y2, x1:x2]


def detect_label_contour(image: np.ndarray) -> np.ndarray | None:
    """
    Fallback label detection using the largest rectangular contour.

    Args:
        image (np.ndarray): BGR image array loaded via OpenCV.

    Returns:
        np.ndarray | None: Cropped region bounded by the largest detected
            contour, or None if no contours were found.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(
        edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest)
    return image[y : y + h, x : x + w]


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------


def preprocess_image(img: np.ndarray) -> np.ndarray:
    """
    Apply CLAHE contrast enhancement, Gaussian denoising, and resize.

    Args:
        img (np.ndarray): BGR image array, typically a cropped label region.

    Returns:
        np.ndarray: Preprocessed grayscale image resized to
            MAX_IMAGE_DIM × MAX_IMAGE_DIM.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrast = clahe.apply(gray)
    denoised = cv2.GaussianBlur(contrast, (3, 3), 0)
    resized = cv2.resize(
        denoised,
        (MAX_IMAGE_DIM, MAX_IMAGE_DIM),
        interpolation=cv2.INTER_CUBIC,
    )
    return resized


def resize_raw(img: np.ndarray, max_dim: int = MAX_IMAGE_DIM) -> np.ndarray:
    """
    Resize a BGR image so its longest side is at most *max_dim*, preserving
    aspect ratio. Never upscales.

    Args:
        img (np.ndarray): Source BGR image array.
        max_dim (int): Maximum allowed pixel dimension on either axis.

    Returns:
        np.ndarray: Resized (or unchanged) BGR image array.
    """
    h, w = img.shape[:2]
    scale = min(max_dim / h, max_dim / w, 1.0)
    if scale < 1.0:
        new_w, new_h = int(w * scale), int(h * scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return img


# ---------------------------------------------------------------------------
# Crop + encode pipeline
# ---------------------------------------------------------------------------


def crop_label(image_path: str) -> np.ndarray:
    """
    Load an image and return the best-effort crop of its nutrition label.

    Tries OCR-based detection, falls back to contour detection, and returns
    the full image if both strategies fail.

    Args:
        image_path (str): Filesystem path to the source image file.

    Returns:
        np.ndarray: Cropped (or full) BGR image array.
    """
    img = cv2.imread(str(image_path))
    label = detect_label_ocr(img)
    if label is None:
        label = detect_label_contour(img)
    if label is None:
        label = img
    return label


def encode_image_array(img: np.ndarray) -> tuple[str, str]:
    """
    Base64-encode an in-memory image array as PNG without writing to disk.

    Args:
        img (np.ndarray): OpenCV-compatible image array (grayscale or BGR).

    Returns:
        tuple[str, str]: ``(base64_string, "image/png")``.
    """
    _, buffer = cv2.imencode(".png", img)
    data = base64.b64encode(buffer).decode()
    return data, "image/png"


def build_image_block(path: str, preprocess: bool = True) -> dict:
    """
    Build an Anthropic API image content block from a file path.

    Args:
        path (str): Filesystem path to the image file.
        preprocess (bool): If True, run OCR crop + CLAHE preprocessing
            (grayscale, 768×768). If False, only aspect-ratio resize the
            raw BGR image.

    Returns:
        dict: Anthropic-compatible image content block ready to embed in
            a ``messages`` payload.
    """
    img = cv2.imread(str(path))

    if preprocess:
        img = crop_label(path)
        img = preprocess_image(img)
    else:
        img = resize_raw(img)

    data, media_type = encode_image_array(img)
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }
