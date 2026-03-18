# ── Build stage ────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps needed to compile some wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ───────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Runtime system libraries only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY app/ ./app/

# PaddleOCR downloads models to ~/.paddleocr on first run.
# Pre-download them here so the container starts cold without network access.
RUN python - <<'EOF'
from paddleocr import PaddleOCR
PaddleOCR(use_angle_cls=False, use_mkldnn=False, lang="en", show_log=False)
EOF

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
