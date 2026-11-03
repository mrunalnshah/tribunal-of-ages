FROM python:3.13-slim
# Pin this to the version `uv --version` prints on your machine, for reproducible builds.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 \
    MODEL_CACHE=/app/models PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# 1. Dependencies only. This layer is reused until uv.lock changes, so rebuilds are fast.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2. Our code and the catalog of themes, then the project itself.
COPY README.md ./
COPY src ./src
COPY providers.toml ./
COPY data/processed/catalog.json ./data/processed/catalog.json
RUN uv sync --frozen --no-dev

# 3. Bake the ONNX models into the image, so a cold start reads them from disk.
RUN python -c "from tribunal.search import Models; Models('/app/models')"

# 4. Hugging Face Spaces runs containers as UID 1000; never run as root anyway.
RUN useradd --create-home --uid 1000 user && chown -R user /app
USER user

EXPOSE 7860
# No access log: the server keeps no record of who asked what.
CMD ["uvicorn", "tribunal.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "7860", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]