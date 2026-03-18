# Nutrition Label API

Extracts structured nutrition facts and ingredients from food product images,
powered by PaddleOCR (label detection) and Claude (data extraction).

---

## Project layout

```
nutrition-api/
├── app/
│   ├── __init__.py
│   ├── main.py        # FastAPI app + routes
│   ├── models.py      # Pydantic request/response schemas
│   ├── ocr.py         # PaddleOCR singleton
│   ├── imaging.py     # Image processing utilities
│   └── analyzer.py    # Claude API call + JSON parsing
├── Dockerfile
├── requirements.txt
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
export ANTHROPIC_API_KEY=sk-ant-...   # Windows: set ANTHROPIC_API_KEY=sk-ant-...

# 4. Run the dev server
uvicorn app.main:app --reload --port 8080
```

Visit `http://localhost:8080/docs` for the interactive Swagger UI.

### Test with curl

```bash
curl -X POST http://localhost:8080/analyze \
  -F "product_image=@Fruit_Loops_Front.jpg" \
  -F "label_image=@Fruit_Loops_Label.jpg"
```

---

## AWS deployment options

### Option A — ECS on Fargate (recommended)

PaddleOCR's model files (~200 MB) and binary deps make this the most
straightforward path.

```bash
# 1. Build and push to ECR
AWS_ACCOUNT=123456789012
AWS_REGION=us-east-1
REPO=nutrition-api

aws ecr create-repository --repository-name $REPO --region $AWS_REGION

aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS \
    --password-stdin $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com

docker build -t $REPO .
docker tag $REPO:latest $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO:latest
docker push $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO:latest

# 2. Create an ECS cluster + Fargate task + ALB via the AWS Console or CDK/Terraform.
#    Key task settings:
#      CPU:    1024  (1 vCPU)
#      Memory: 3072  (3 GB — PaddleOCR needs headroom)
#      Port:   8080
#
#    Environment variable to set on the task:
#      ANTHROPIC_API_KEY  →  use AWS Secrets Manager reference, not plaintext
```

### Option B — AWS Lambda (cold-start caveat)

The app includes a `Mangum` handler so it works with Lambda + API Gateway.
However, PaddleOCR models are ~200 MB, which exceeds the Lambda 50 MB zip
limit. Use a **container image Lambda** (up to 10 GB):

```bash
# Same ECR push as above, then:
aws lambda create-function \
  --function-name nutrition-api \
  --package-type Image \
  --code ImageUri=$AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO:latest \
  --role arn:aws:iam::$AWS_ACCOUNT:role/lambda-execution-role \
  --timeout 60 \
  --memory-size 3008 \
  --environment "Variables={ANTHROPIC_API_KEY=<from-secrets-manager>}"
```

Wire an **HTTP API Gateway** trigger to the function. The `Mangum` adapter
in `app/main.py` (`handler = Mangum(app)`) translates Lambda events to ASGI.

> **Cold start note**: Lambda will spin up a new container when idle.
> PaddleOCR model loading adds ~4 s to cold starts. Use **Provisioned
> Concurrency** if latency SLAs require it.

### Secrets management

Never pass `ANTHROPIC_API_KEY` as a plaintext env var in production.
Use **AWS Secrets Manager** and reference it in your task definition:

```json
{
  "secrets": [
    {
      "name": "ANTHROPIC_API_KEY",
      "valueFrom": "arn:aws:secretsmanager:us-east-1:123456789012:secret:anthropic-key"
    }
  ]
}
```

---

## API reference

### `GET /health`
Returns `{"status": "ok"}`. Used by ALB and ECS health checks.

### `POST /analyze`
Upload two images as `multipart/form-data`.

| Field           | Type | Description                        |
|-----------------|------|------------------------------------|
| `product_image` | file | Front-of-pack image (JPEG/PNG/WebP)|
| `label_image`   | file | Nutrition label image              |

**Response `200`**
```json
{
  "product_info": { "brand": "...", "product_name": "...", ... },
  "nutrition_facts": { "serving_size": { "value": 39, "unit": "g" }, ... },
  "ingredients": { "raw_text": "...", "items": [...], ... }
}
```

**Error codes**

| Code | Reason                                    |
|------|-------------------------------------------|
| 400  | Unsupported file type or unreadable image |
| 500  | Claude API failure or JSON parse error    |
