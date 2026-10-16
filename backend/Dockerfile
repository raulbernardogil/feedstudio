FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini run_dev.py ./
COPY migrations ./migrations
COPY feedstudio ./feedstudio

RUN useradd --create-home --uid 10001 feedstudio && mkdir -p /data && chown feedstudio /data
USER feedstudio

ENV FEEDSTUDIO_STORAGE_DIR=/data/storage HOST=0.0.0.0 PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

# Applies migrations, then serves the API.
CMD ["python", "run_dev.py"]
