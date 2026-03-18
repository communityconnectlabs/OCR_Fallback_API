"""
Lazy singleton wrapper around PaddleOCR.

PaddleOCR model loading is expensive (~2-4 s). We initialise it once at
application startup via ``init_ocr_engine()`` and expose ``get_ocr_engine()``
for use in the rest of the codebase.
"""

from __future__ import annotations

from paddleocr import PaddleOCR

_ocr_engine: PaddleOCR | None = None


def init_ocr_engine() -> None:
    """
    Load the PaddleOCR model into the module-level singleton.

    Should be called exactly once during application startup (e.g. from a
    FastAPI lifespan handler). Subsequent calls are no-ops.
    """
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = PaddleOCR(
            use_angle_cls=False,   # not needed for upright nutrition labels
            use_mkldnn=False,      # avoids OneDNN compatibility issues
            lang="en",
            show_log=False,
        )


def get_ocr_engine() -> PaddleOCR:
    """
    Return the initialised OCR engine.

    Returns:
        PaddleOCR: The module-level singleton.

    Raises:
        RuntimeError: If ``init_ocr_engine()`` has not been called yet.
    """
    if _ocr_engine is None:
        raise RuntimeError(
            "OCR engine is not initialised. "
            "Call init_ocr_engine() at application startup."
        )
    return _ocr_engine
