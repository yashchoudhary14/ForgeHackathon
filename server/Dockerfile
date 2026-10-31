FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    AGENT_HEADLESS=true \
    STORAGE_DIR=/tmp/adhikaar \
    HOME=/home/user \
    PORT=7860

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt \
    && playwright install --with-deps chromium \
    && useradd --create-home --uid 1000 user \
    && mkdir -p /tmp/adhikaar \
    && chown user:user /tmp/adhikaar

COPY --chown=user:user app ./app
COPY --chown=user:user scripts ./scripts
USER user
EXPOSE 7860
HEALTHCHECK --interval=60s --timeout=5s --start-period=90s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '7860') + '/api/health', timeout=4)"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1"]
