"""Application configuration.

Every setting is read from an environment variable. Nothing is hardcoded and
nothing is read from a config file baked into the image — that is the twelfth-
factor rule, and it is what lets the *same* image run in dev, staging, and prod
with only the environment differing. If you find yourself wanting to rebuild an
image to change a value, the value belongs here instead.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- database -----------------------------------------------------------
    # psycopg3 driver. The hostname "db" resolves via Docker Compose's network
    # locally, and via a Kubernetes Service later — same URL shape either way.
    database_url: str = "postgresql+psycopg://shortener:shortener@db:5432/shortener"
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # --- identity -----------------------------------------------------------
    # Injected at build time by CI so /version can prove exactly which commit
    # is serving traffic. This is what makes a deploy verifiable rather than
    # something you assume worked.
    app_version: str = "0.0.0-dev"
    git_sha: str = "unknown"

    # --- behaviour ----------------------------------------------------------
    base_url: str = "http://localhost:8000"
    shortcode_length: int = 7
    shortcode_max_attempts: int = 5
    cache_size: int = 1024

    # --- observability ------------------------------------------------------
    environment: str = "local"
    # Empty means tracing is disabled. The app must run identically on a laptop
    # with no collector and in a cluster that has one.
    otlp_endpoint: str = ""
    # 1.0 is fine at this volume. In production this is the dial that controls
    # how much tracing costs — traces are the most expensive signal per event.
    trace_sample_ratio: float = 1.0

    # --- operational --------------------------------------------------------
    log_level: str = "INFO"
    # Off by default. The failure-injection endpoints must never be reachable
    # in an environment that matters; the dev overlay is the only place this
    # gets flipped on.
    enable_debug_endpoints: bool = False


@lru_cache
def get_settings() -> Settings:
    """Cached so the environment is parsed once per process, not per request."""
    return Settings()
