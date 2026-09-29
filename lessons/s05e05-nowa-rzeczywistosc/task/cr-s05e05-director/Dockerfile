FROM python:3.13.5-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.6.5 /uv /uvx /bin/

COPY pyproject.toml ./
RUN uv sync --frozen --no-cache || uv sync --no-cache

COPY . .

CMD ["sh", "-c", "uv run uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
