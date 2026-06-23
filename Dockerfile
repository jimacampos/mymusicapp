# syntax=docker/dockerfile:1

# ---- Stage 1: build the React/Vite frontend -------------------------------
FROM node:22-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime serving API + built UI -----------------------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Backend code. main.py serves ../frontend/dist, so preserve that layout.
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist

EXPOSE 8000

# App Service for Containers injects PORT (mirror it with the WEBSITES_PORT
# app setting). Fall back to 8000 for local `docker run`.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
