# SNAPSMART Fallback API

Extracts structured nutrition facts and ingredients from food product images,
powered by PaddleOCR (label detection) and Claude (data extraction).

---

## Project layout (Basic)

```
LABEL_POC_API/
├── fallback_project/
│   ├── __init__.py
│   ├── main.py            # FastAPI app + routes
│   ├── models.py          # Pydantic request/response schemas
│   ├── ocr.py             # PaddleOCR singleton
│   ├── imaging.py         # Image processing utilities
│   └── analyzer.py        # Claude API call + JSON parsing
├── Dockerfile
├── requirements.txt
├── .env
└── README.md
```

---

## Local development

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your Anthropic key
# Make sure you have an .env file with the ANTHROPIC_API_KEY value in there.

# 4. Run the dev server
uvicorn fallback_project.main:app --reload --port 8080
```

---

## Docker (without database)

### Build

```bash
docker build -t fallback_ocr .
```

### Run

```bash
docker run -p 8080:8080 --env-file .env fallback_ocr
```

### Health check

```bash
curl http://localhost:8080/health
```

### Analyze a product

```bash
# Linux / macOS
curl -X POST http://localhost:8080/analyze \
  -F "product_image=@Fruit_Loops_Front.jpg" \
  -F "label_image=@Fruit_Loops_Label.jpg"

# Windows PowerShell
curl.exe -X POST http://localhost:8080/analyze `
  -F "product_image=@Fruit_Loops_Front.jpg" `
  -F "label_image=@Fruit_Loops_Label.jpg"
```

### Swagger UI

Visit `http://localhost:8080/docs` for the interactive Swagger UI.

---

## Project layout (with DB)

```
LABEL_POC_API/
├── fallback_project/
│   ├── __init__.py
│   ├── main.py            # FastAPI app + routes
│   ├── main_with_db.py    # FastAPI app + routes + DB write/read
│   ├── models.py          # Pydantic request/response schemas
│   ├── ocr.py             # PaddleOCR singleton
│   ├── imaging.py         # Image processing utilities
│   ├── analyzer.py        # Claude API call + JSON parsing
│   └── postgres_client.py # PostgreSQL client
├── Dockerfile_with_db
├── entrypoint_with_db.sh
├── init.sql
├── requirements_with_db.txt
├── .env
└── README.md
```

---

## Docker (with database)

Spins up a FastAPI server and an internal PostgreSQL instance in the same
container. On first run the database, user, and table are created automatically.
Analyzed products are written to the database if the product name is not already
present.

### .env requirements

```
ANTHROPIC_API_KEY=sk-ant-...
DB_HOST=localhost
DB_PORT=5432
DB_NAME=nutrition_and_ingredients_db
DB_USER=snapuser
DB_PASSWORD=pwforsnap
DB_TABLE=nutrition_and_ingredients_tbl
```

### Build

```bash
docker build -f Dockerfile_with_db -t fallback_ocr_db .
```

### Run

```bash
docker run -p 8080:8080 --env-file .env fallback_ocr_db
```

To persist the database between container restarts, mount a volume:

```bash
docker run -p 8080:8080 --env-file .env -v nutrition_pgdata:/var/lib/postgresql/data fallback_ocr_db
```

### Health check

```bash
curl http://localhost:8080/health
```

### Analyze a product and write to DB

```bash
# Linux / macOS
curl -X POST http://localhost:8080/analyze \
  -F "product_image=@Fruit_Loops_Front.jpg" \
  -F "label_image=@Fruit_Loops_Label.jpg"

# Windows PowerShell
curl.exe -X POST http://localhost:8080/analyze `
  -F "product_image=@Fruit_Loops_Front.jpg" `
  -F "label_image=@Fruit_Loops_Label.jpg"
```

The response includes a `db_status` field indicating the result of the DB write:
- `inserted` — product was new and written to the database
- `already_exists` — product name was already in the database, skipped
- `skipped_no_product_name` — Claude could not extract a product name

### Analyze without saving to DB

```bash
# Linux / macOS
curl -X POST "http://localhost:8080/analyze?save_to_db=false" \
  -F "product_image=@Fruit_Loops_Front.jpg" \
  -F "label_image=@Fruit_Loops_Label.jpg"

# Windows PowerShell
curl.exe -X POST "http://localhost:8080/analyze?save_to_db=false" `
  -F "product_image=@Fruit_Loops_Front.jpg" `
  -F "label_image=@Fruit_Loops_Label.jpg"
```

### Fetch products from the database

```bash
# Fetch last 10 products
curl http://localhost:8080/products

# Fetch last 5 products
curl "http://localhost:8080/products?n=5"

# Filter by product name
curl "http://localhost:8080/products?product_name=Froot+Loops"

# Windows PowerShell
curl.exe http://localhost:8080/products
curl.exe "http://localhost:8080/products?product_name=Froot+Loops&n=5"
```

### Swagger UI

Visit `http://localhost:8080/docs` for the interactive Swagger UI.

---