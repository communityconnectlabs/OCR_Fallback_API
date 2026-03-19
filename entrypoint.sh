#!/bin/sh
echo "Warming up PaddleOCR models..."
python -c "from paddleocr import PaddleOCR; PaddleOCR(use_angle_cls=True, use_mkldnn=True, lang='en', show_log=False)"
echo "Starting server..."
exec uvicorn fallback_project.main:app --host 0.0.0.0 --port 8080