# Minimal Dockerfile for Public Verify Service
# This service only exposes /verify/{batch_id} endpoints
# NO authentication, NO processing - read-only Firestore access

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY main.py .

# Cloud Run uses PORT env var
ENV PORT=8080

# Run with uvicorn
CMD ["python", "main.py"]
