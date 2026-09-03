# DiffEQ Engine — one image with everything the app needs:
# Python runtime + numpy/scipy/sympy + FastAPI engine + bilingual UI.
# End users only need a browser; the host only needs Docker.
#
#   docker build -t diffeq-engine .
#   docker run -p 8000:8000 diffeq-engine
FROM python:3.11-slim

WORKDIR /app

# Declare dependencies first so rebuilds reuse the cached layer.
COPY requirements.txt ./
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Engine, API, local intelligence, and the self-contained web UI.
COPY api/ ./api/
COPY web/ ./web/

ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
