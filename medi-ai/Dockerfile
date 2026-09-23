# MediAI production image (TASK-012 release).
# python:3.12-slim, non-root, uvicorn with workers, no reload.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps kept minimal (Pillow needs libjpeg/zlib; slim already ships them).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Writable uploads dir for the photo envelope (TTL-swept, git-ignored in repo).
RUN mkdir -p /app/app/uploads && \
    useradd -m -u 10001 appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Production server: multiple workers, bind-all (container), no --reload.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
