# Agenclave - single-image deploy. Builds the React UI, then serves UI + API from
# one uvicorn process (see api/main.py:_mount_frontend). Torch-free runtime image.

# ---- Stage 1: build the React bundle into frontend/dist ----
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: python runtime serving UI + API ----
FROM python:3.11-slim AS runtime
WORKDIR /app

# ROOT (config.py) resolves to /app, so models/, results/, data/ and frontend/dist
# must live under /app.
ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements-serve.txt ./
RUN pip install --no-cache-dir -r requirements-serve.txt

# Application code + trained model + the committed demo run (/runs/latest).
COPY src/ ./src/
COPY models/ ./models/
COPY results/ ./results/

# SQLite db is created here at startup (DATA_DIR = ROOT/data).
RUN mkdir -p /app/data

# Built SPA from the web stage.
COPY --from=web /web/dist ./frontend/dist

# Host injects $PORT (Render/Railway/Fly); default 8000 for local `docker run`.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn agenclave.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
