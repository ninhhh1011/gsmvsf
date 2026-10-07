FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml .

# Install from pyproject.toml (not requirements.txt which is auto-generated)
RUN pip install --no-cache-dir -e .

# Copy application code
COPY backend/app/ ./backend/app/

ENV PYTHONPATH=/app
ENV LOG_LEVEL=INFO

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
