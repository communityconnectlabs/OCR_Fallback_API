import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from mangum import Mangum

from .analyzer import analyze_food_product
from .models import AnalysisResponse, ErrorResponse, HealthResponse
from .ocr import init_ocr_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize heavy resources once at startup."""
    init_ocr_engine()
    yield


app = FastAPI(
    title="Nutrition Label API",
    description="Extract nutrition facts and ingredients from food product images.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
)
async def health():
    """Returns service status. Used by ALB / ECS health checks."""
    return HealthResponse(status="ok")


@app.post(
    "/analyze",
    response_model=AnalysisResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Analyze a food product",
    description=(
        "Upload a product image and a nutrition label image. "
        "Returns structured nutrition facts and ingredients."
    ),
)
async def analyze(
    product_image: UploadFile = File(
        ...,
        description="Front-of-pack product image (JPEG, PNG, or WebP).",
    ),
    label_image: UploadFile = File(
        ...,
        description="Nutrition label image (JPEG, PNG, or WebP).",
    ),
):
    """
    Analyze a food product from two uploaded images.

    Args:
        product_image (UploadFile): Front-of-pack product image.
        label_image (UploadFile):   Nutrition label / back-of-pack image.

    Returns:
        AnalysisResponse: Structured product info, nutrition facts,
            and ingredients parsed from the label.

    Raises:
        HTTPException 400: Unsupported file type or unreadable image.
        HTTPException 500: Upstream API failure or JSON parse error.
    """
    _validate_content_type(product_image)
    _validate_content_type(label_image)

    suffix_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }

    try:
        with (
            tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix_map[product_image.content_type],
            ) as tmp_prod,
            tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix_map[label_image.content_type],
            ) as tmp_label,
        ):
            tmp_prod.write(await product_image.read())
            tmp_label.write(await label_image.read())
            prod_path = tmp_prod.name
            label_path = tmp_label.name

        result = analyze_food_product(prod_path, label_path)

        return AnalysisResponse(**result)

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Model returned non-JSON response: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        for path in (prod_path, label_path):
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass


def _validate_content_type(upload: UploadFile) -> None:
    """
    Raise HTTP 400 if the uploaded file is not a supported image type.

    Args:
        upload (UploadFile): The incoming file to validate.

    Raises:
        HTTPException: If content_type is not jpeg, png, or webp.
    """
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if upload.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{upload.content_type}'. "
                   f"Allowed: {', '.join(sorted(allowed))}",
        )


# AWS Lambda handler — ignored when running with uvicorn directly.
handler = Mangum(app)
