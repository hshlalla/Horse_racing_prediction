FROM python:3.9-slim
WORKDIR /app

# Install dependencies needed for asyncpg / building
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Copy python project definitions
COPY backend/pyproject.toml /app/

# Install dependencies (no-root to only install deps, not the package itself if not needed, but pip install . works too)
RUN pip install --no-cache-dir . || pip install --no-cache-dir build && pip install --no-cache-dir .

COPY backend/ /app/
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
