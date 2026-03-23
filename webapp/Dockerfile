FROM python:3.14-slim

# Copy uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy project files
COPY config.json .
COPY frontend/ frontend/
COPY backend/ backend/

WORKDIR /app/backend
ENV UV_COMPILE_BYTECODE=1
ENV PATH="/app/backend/.venv/bin:$PATH"

# Install dependencies using uv
RUN uv sync --python 3.14 --frozen

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
