FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required by unstructured.io for PDF processing and OCR
RUN apt-get update && apt-get install -y libgl1 tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-tra poppler-utils build-essential

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]