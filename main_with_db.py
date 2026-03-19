import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, Query
from fastapi.responses import JSONResponse
from mangum import Mangum

from .analyzer import analyze_food_product
from .models import AnalysisResponse, ErrorResponse, HealthResponse
from .ocr import init_ocr_engine
from .postgres_client import PostgresClient

from dotenv import load_dotenv
load_dotenv()

def get_db() -> PostgresClient:
    return PostgresClient(
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 5432)),
        db_name=os.environ.get("DB_NAME", "nutrition_and_ingredients_db"),
        table_name=os.environ.get("DB_TABLE", "nutrition_and_ingredients_tbl"),
    )

def product_exists(db: PostgresClient, product_name: str) -> bool:
    rows = db.fetch_n_rows_from_table(
        where_conditions={"product_name": product_name},
        n=1,
    )
    return len(rows) > 0

def build_db_record(result: dict) -> dict:
    pi = result.get("product_info", {})
    nf = result.get("nutrition_facts", {}).get("per_serving", {})
    ing = result.get("ingredients", {})

    return {
        "brand":                  pi.get("brand"),
        "product_name":           pi.get("product_name"),
        "packaging_type":         pi.get("packaging_type"),
        "preparation_state":      pi.get("preparation_state"),
        "calories":               nf.get("calories"),
        "total_fat_g":            nf.get("total_fat_g"),
        "saturated_fat_g":        nf.get("saturated_fat_g"),
        "trans_fat_g":            nf.get("trans_fat_g"),
        "cholesterol_mg":         nf.get("cholesterol_mg"),
        "sodium_mg":              nf.get("sodium_mg"),
        "total_carbohydrate_g":   nf.get("total_carbohydrate_g"),
        "dietary_fiber_g":        nf.get("dietary_fiber_g"),
        "total_sugars_g":         nf.get("total_sugars_g"),
        "added_sugars_g":         nf.get("added_sugars_g"),
        "protein_g":              nf.get("protein_g"),
        "ingredients_raw":        ing.get("raw_text"),
        "contains_allergens":     ing.get("contains_allergens"),
        "may_contain_allergens":  ing.get("may_contain_allergens"),
    }

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
    return HealthResponse(status="ok")

@app.get(
    "/products",
    summary="Fetch products from the database",
    description="Returns the last n analyzed products. Optionally filter by product_name.",
)
async def get_products(
    n: int = Query(default=10, ge=1, le=100, description="Number of rows to return."),
    product_name: str | None = Query(default=None, description="Filter by exact product name."),
):
    try:
        db = get_db()
        where = {"product_name": product_name} if product_name else None
        rows = db.fetch_n_rows_from_table(
            where_conditions=where,
            n=n,
            return_results_formatted=True,
        )
        return {"count": len(rows), "products": rows}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.post(
    "/analyze",
    response_model=AnalysisResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Analyze a food product",
    description=(
        "Upload a product image and a nutrition label image. "
        "Returns structured nutrition facts and ingredients. "
        "Writes to the database only if the product_name is not already present."
    ),
)
async def analyze(
    product_image: UploadFile = File(..., description="Front-of-pack product image (JPEG, PNG, or WebP)."),
    label_image: UploadFile = File(..., description="Nutrition label image (JPEG, PNG, or WebP)."),
    save_to_db: bool = Query(default=True, description="Write result to DB if product not already stored."),
):
    _validate_content_type(product_image)
    _validate_content_type(label_image)

    suffix_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }

    prod_path = label_path = None

    try:
        with (
            tempfile.NamedTemporaryFile(delete=False, suffix=suffix_map[product_image.content_type]) as tmp_prod,
            tempfile.NamedTemporaryFile(delete=False, suffix=suffix_map[label_image.content_type]) as tmp_label,
        ):
            tmp_prod.write(await product_image.read())
            tmp_label.write(await label_image.read())
            prod_path = tmp_prod.name
            label_path = tmp_label.name

        result = analyze_food_product(prod_path, label_path)

        if save_to_db:
            product_name = result.get("product_info", {}).get("product_name")
            if product_name:
                db = get_db()
                if not product_exists(db, product_name):
                    record = build_db_record(result)
                    db.insert_values_into_table(record)
                    result["db_status"] = "inserted"
                else:
                    result["db_status"] = "already_exists"
            else:
                result["db_status"] = "skipped_no_product_name"

        return AnalysisResponse(**result)

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Model returned non-JSON response: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        for path in (prod_path, label_path):
            if path:
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass

def _validate_content_type(upload: UploadFile) -> None:
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if upload.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{upload.content_type}'. Allowed: {', '.join(sorted(allowed))}",
        )

handler = Mangum(app)