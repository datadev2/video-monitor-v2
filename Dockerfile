FROM python:3.13.7-slim-bookworm AS base

RUN apt-get update && apt-get install -y \
    ffmpeg \
    ca-certificates \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*



# ---------- BUILDER ----------
FROM base AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8.14 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

COPY uv.lock pyproject.toml /app/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY . /app

# ---------- RUNTIME ----------
FROM base

RUN groupadd -g 1000 prod \
    && useradd -m -u 1000 -g prod -s /bin/bash prod

WORKDIR /app

COPY --from=builder /app /app

RUN chown -R prod:prod /app

# Celery beat persists its schedule here. The directory must exist in the
# image and be owned by prod: docker copies ownership from the image path
# when it creates a fresh named volume, and a root-owned /data would leave
# beat unable to write its state.
RUN mkdir -p /data && chown prod:prod /data

ENV PATH="/app/.venv/bin:$PATH"

USER prod

