# Use the official Python image with the exact version required
FROM python:3.13.5-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Copy the project files
COPY . .

# Install dependencies using uv
RUN uv sync --frozen

# Cloud Run sets the PORT environment variable at runtime.
CMD ["sh", "-c", "uv run uvicorn main:app --host 0.0.0.0 --port $PORT"]
