# syntax=docker/dockerfile:1.7
#
# Multi-stage build for the FastAPI backend.
#
# Stage 1 resolves and installs dependencies into a virtualenv. Stage 2 copies
# that virtualenv into a clean runtime image. The point is that uv, build
# toolchains, and package caches never reach the final image — they are build
# inputs, not runtime requirements. Shipping them would mean a larger image and
# a larger attack surface, and every one of those extra packages is something
# Trivy will have an opinion about.

# ---------------------------------------------------------------------------
# Stage 1 — builder
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS builder

# Copy the statically-linked uv binary from its official image rather than
# pip-installing it. Faster, and it pins uv's version independently of whatever
# pip would resolve today.
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# MUST match the runtime WORKDIR.
#
# uv writes absolute paths into the venv: every console script gets a
# `#!/app/.venv/bin/python` shebang, and pyvenv.cfg records the location. Build
# at /build and copy to /app and those paths dangle — the kernel then fails the
# exec and reports "no such file or directory" for the *script*, not for the
# missing interpreter. That error sends you looking for alembic, which is
# present and fine.
WORKDIR /app

# Dependency files first, source second. Docker caches layers by content, so as
# long as pyproject.toml and uv.lock are unchanged, the (slow) dependency
# install is reused and only the (fast) source copy re-runs. Copying source
# first would invalidate the dependency layer on every single code edit — the
# most common reason people's builds are slow.
COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

# Non-root. A container process running as uid 0 that escapes its namespace is
# root on the node; running as a normal user is the single cheapest hardening
# step available and is checked by essentially every image scanner.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home app

# curl is here only for HEALTHCHECK. It is a deliberate trade: a slightly larger
# image in exchange for a container that can report its own health to Docker.
# Kubernetes uses its own probes and does not need this, so the Kubernetes
# manifests do not rely on it.
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv ./.venv
COPY --from=builder --chown=app:app /app/app ./app
COPY --from=builder --chown=app:app /app/alembic ./alembic
COPY --from=builder --chown=app:app /app/alembic.ini ./

# Build metadata, injected by CI. Declared after the COPY layers so changing the
# SHA does not invalidate them — otherwise every commit would rebuild the whole
# image from scratch.
ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA}

# OCI labels. `source` and `revision` are what make a running container
# traceable back to the exact commit that produced it.
LABEL org.opencontainers.image.title="url-shortener-backend" \
      org.opencontainers.image.source="https://github.com/sudhamshrama/url-shortener" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.licenses="MIT"

USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD curl --fail --silent http://localhost:8000/health || exit 1

# Exec form, no shell. A shell-form CMD makes the shell PID 1, which then does
# not forward SIGTERM — so the container ignores `docker stop` and Kubernetes'
# graceful shutdown, and gets SIGKILLed after the grace period instead. In-flight
# requests are dropped. This is the single most common containerisation bug.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
