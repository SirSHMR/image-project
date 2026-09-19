FROM python:3.11-slim

# ExifTool is the core metadata-extraction engine used by the backend
RUN apt-get update \
    && apt-get install -y --no-install-recommends libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
EXPOSE 8000

# Render injects $PORT at runtime; fall back to 8000 for local docker run.
# Using "python -m uvicorn" (instead of the bare "uvicorn" entrypoint)
# ensures the current directory is on sys.path, so the local "app"
# package is importable.
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
