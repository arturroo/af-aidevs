FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies using the token (passed as build arg)
ARG UV_INDEX_GAR_PASSWORD
ENV UV_INDEX_GAR_USERNAME=oauth2accesstoken
ENV UV_INDEX_GAR_PASSWORD=$UV_INDEX_GAR_PASSWORD

RUN uv sync

# Copy source code
COPY . .

# Run the app
CMD uv run --no-sync uvicorn main:app --host 0.0.0.0 --port $PORT
