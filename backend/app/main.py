"""Application entrypoint.

Route registration order matters here and is the one non-obvious thing in the
file: the catch-all `/{code}` redirect lives in the links router and must be
registered after everything else, or it will shadow /health, /ready, /version,
and /debug/*.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.cache import LRUCache
from app.config import get_settings
from app.database import engine
from app.observability import configure_logging, configure_metrics, configure_tracing
from app.routes import debug, health, links

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings)
    log = logging.getLogger(__name__)

    # Replace the module-level default with one sized from configuration.
    links.cache = LRUCache(maxsize=settings.cache_size)

    log.info(
        "starting url-shortener version=%s sha=%s debug_endpoints=%s",
        settings.app_version,
        settings.git_sha,
        settings.enable_debug_endpoints,
    )
    yield
    log.info("shutting down")


app = FastAPI(
    title="url-shortener",
    version=settings.app_version,
    lifespan=lifespan,
    # Swagger stays on: it is free documentation and makes the API explorable
    # during a demo without reaching for curl.
    docs_url="/docs",
)

# The frontend is served from a different origin (nginx on :80 vs the API on
# :8000) during local development, so the browser will preflight. In Kubernetes
# both sit behind one ingress and this becomes a no-op.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

configure_metrics(app)
configure_tracing(app, settings, engine)

app.include_router(health.router)

if settings.enable_debug_endpoints:
    app.include_router(debug.router)

# LAST. See module docstring.
app.include_router(links.router)
