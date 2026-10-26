# Production image for single-service hosting such as Render (decision 0004).
# Local development keeps using docker-compose.yml and backend/Dockerfile.

# ---- 1. Build the React app
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Python API + worker serving the built app
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH" \
    FRONTEND_DIST_PATH=/app/static \
    DEMO_DATA_PATH=/demo-data \
    DOCUMENT_STORE_PATH=/data/documents

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY backend/ ./
COPY demo-data/ /demo-data/
COPY --from=web /web/dist /app/static

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /data/documents \
    && chown -R app /data /app \
    && sed -i 's/\r$//' /app/start.sh && chmod +x /app/start.sh
USER app

EXPOSE 8000
CMD ["/app/start.sh"]
