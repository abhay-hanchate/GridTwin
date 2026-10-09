# GridTwin v2: the API and the v2 dashboard in one container (P10.10, F6).
#   docker build -t gridtwin:v2 .
#   docker run -p 8000:8000 gridtwin:v2            # offline demo: serves only the precomputed results
#   docker run -p 8000:8000 -e GRIDTWIN_OFFLINE=0 gridtwin:v2   # computes on demand
# Online, /readiness also wants data/processed/v2 (built by scripts/build_data.py, not in git): an image built from a
# clean checkout serves the offline demo and computes on demand, but reports not ready in online mode.

# ---- 1. the dashboard -----------------------------------------------------------------------------------------
FROM node:24-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. the API -----------------------------------------------------------------------------------------------
FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GRIDTWIN_ENV=prod \
    GRIDTWIN_OFFLINE=1 \
    GRIDTWIN_CORS_ORIGINS=http://localhost:8000
# LightGBM needs the OpenMP runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt constraints.txt ./
RUN pip install -r requirements.txt -c constraints.txt

RUN useradd --create-home --uid 10001 gridtwin
COPY backend/ backend/
COPY engine/ engine/
COPY ml/ ml/
COPY scripts/ scripts/
COPY data/processed/ data/processed/
COPY data/results/ data/results/
COPY --from=frontend /src/frontend/dist frontend/dist
# Only the result cache and the monitor state are written at run time.
RUN mkdir -p data/monitor && chown -R gridtwin:gridtwin data/results data/monitor
USER gridtwin

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v2/health', timeout=4)"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
