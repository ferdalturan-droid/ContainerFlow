# ─────────────────────────────────────────────────────────────
# ContainerFlow — Production Dockerfile (Scaleway Serverless Containers)
# Multi-stage: build React → serve everything from FastAPI/uvicorn
# ─────────────────────────────────────────────────────────────

# ---------- Stage 1: Frontend build ----------
FROM node:20-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/yarn.lock* frontend/package-lock.json* ./
RUN (yarn install --frozen-lockfile 2>/dev/null || npm ci --legacy-peer-deps)
COPY frontend/ ./
# REACT_APP_BACKEND_URL empty => frontend calls same-origin /api (correct for single container)
ENV REACT_APP_BACKEND_URL=""
RUN (yarn build 2>/dev/null || npm run build)

# ---------- Stage 2: Backend + static serving ----------
FROM python:3.11-slim AS runtime
WORKDIR /app

# System deps for Pillow/pillow-heif (photo handling)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libheif1 libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /build/build ./frontend_build


COPY scaleway-mongo-ca.pem /app/scaleway-mongo-ca.pem

EXPOSE 8080
ENV PORT=8080

# Scaleway health checks hit / — uvicorn serves both API (/api/*) and React SPA (everything else)
CMD ["sh", "-c", "cd backend && uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
