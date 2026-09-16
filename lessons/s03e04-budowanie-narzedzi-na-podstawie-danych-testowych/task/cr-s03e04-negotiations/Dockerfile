# Use the official Python image with the exact version required
FROM python:3.13.5-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Copy dependency files
COPY pyproject.toml README.md* ./

# Install dependencies using the token (passed as build arg)
ARG UV_INDEX_GAR_PASSWORD
ENV UV_INDEX_GAR_USERNAME=oauth2accesstoken
ENV UV_INDEX_GAR_PASSWORD=$UV_INDEX_GAR_PASSWORD

RUN uv sync --no-install-project

# Copy source code (respects .dockerignore)
COPY . .

RUN uv sync

# Run the app
CMD ["sh", "-c", "uv run uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
