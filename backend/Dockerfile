FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml .

RUN pip install --no-cache-dir "uvicorn[standard]>=0.32.0" \
    "fastapi>=0.115.0" \
    "pydantic>=2.9.0" \
    "pydantic-settings>=2.6.0" \
    "httpx>=0.27.0" \
    "structlog>=24.0.0"

COPY backend/ ./backend/

ENV PYTHONPATH=/app
ENV LOG_LEVEL=INFO

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
