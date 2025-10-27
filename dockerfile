FROM python:3.11.14-slim

WORKDIR /app

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && pip install --upgrade pip

RUN groupadd -r appuser && \
    useradd -r -g appuser -u 1000 appuser && \
    chown -R appuser:appuser /app

COPY --chown=appuser:appuser pyproject.toml ./
RUN pip install --no-cache-dir .

COPY --chown=appuser:appuser src/ ./src/

USER appuser

EXPOSE 8000

CMD ["python", "src/server.py", "--transport", "stdio"]