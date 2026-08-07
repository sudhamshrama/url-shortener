"""Metrics, tracing, and structured logging.

Three signals, three jobs:

  * **Metrics** answer "is it broken, and how badly" — cheap, aggregated, and
    what alerts fire on.
  * **Logs** answer "what exactly happened to this one request" — expensive per
    event, but carry detail metrics cannot.
  * **Traces** answer "where did the time go" — which of five services, or which
    database query, actually caused the latency.

The thing that makes them useful together is the trace ID: it appears in the
log lines and in the trace, so a spike on a dashboard leads to the exact
request, which leads to the exact slow span.

A note on cardinality, since it is the mistake that takes metrics systems down:
every distinct label value creates a new time series. Putting the short code in
a metric label would create one series per link — millions of them — and
Prometheus would exhaust memory. Codes belong in logs and traces, never in
labels.
"""

import logging
import sys
from typing import Any

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from prometheus_client import Counter, Gauge
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import Settings

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Business metrics
#
# RED metrics come free from the instrumentator. These are the ones that say
# something about the product rather than the plumbing — and they are what make
# a Grafana dashboard interesting rather than generic.
# --------------------------------------------------------------------------

links_created_total = Counter(
    "shortener_links_created_total",
    "Short links created",
    # Bounded label set: exactly two values, ever. Safe.
    ["code_type"],
)

redirects_total = Counter(
    "shortener_redirects_total",
    "Redirects served",
    # "hit" or "miss" — again bounded. The code itself is deliberately absent.
    ["cache"],
)

redirect_misses_total = Counter(
    "shortener_redirect_not_found_total",
    "Redirect requests for codes that do not exist",
)

cache_size = Gauge(
    "shortener_cache_entries",
    "Entries currently held in the in-process link cache",
)

cache_hit_ratio = Gauge(
    "shortener_cache_hit_ratio",
    "Cumulative cache hit ratio for this process",
)


def configure_logging(settings: Settings) -> None:
    """JSON logs to stdout, with the trace ID on every line.

    Containers do not manage log files — the runtime captures stdout and the
    platform ships it onward. Writing to a file inside a container means the
    logs die with the pod.

    JSON rather than a bespoke text format because Loki (and anything else)
    can then extract fields without a fragile regex. The trace ID is what lets
    you pivot from a log line straight to the trace.
    """

    class TraceContextFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            span = trace.get_current_span()
            ctx = span.get_span_context()
            # A 0 trace ID means "no active span" — background work, or a log
            # emitted before instrumentation was installed.
            trace_id = format(ctx.trace_id, "032x") if ctx.trace_id else ""
            span_id = format(ctx.span_id, "016x") if ctx.span_id else ""

            payload: dict[str, Any] = {
                "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
            }
            if trace_id:
                payload["trace_id"] = trace_id
                payload["span_id"] = span_id
            if record.exc_info:
                payload["exception"] = self.formatException(record.exc_info)

            import json

            return json.dumps(payload)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(TraceContextFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # Uvicorn installs its own handlers on its own loggers with propagate=False,
    # so configuring root alone leaves every access log emitting uvicorn's plain
    # text format — no JSON, and critically no trace_id. The result looks fine
    # in `kubectl logs` and quietly destroys the logs-to-traces correlation that
    # is the entire reason for structured logging.
    #
    # Clearing their handlers and re-enabling propagation routes them through
    # the formatter above.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "gunicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True


def configure_tracing(app: FastAPI, settings: Settings, engine: Any) -> None:
    """Install OpenTelemetry tracing, if an OTLP endpoint is configured.

    No endpoint means tracing is silently skipped rather than failing — the app
    must run on a laptop with no collector, and in Compose, and in a cluster
    that has one.
    """
    if not settings.otlp_endpoint:
        logger.info("tracing disabled (no OTLP endpoint configured)")
        return

    resource = Resource.create(
        {
            "service.name": "url-shortener-backend",
            "service.version": settings.app_version,
            "deployment.environment": settings.environment,
        }
    )

    # Sampling. At 100% every request produces a trace, which is fine at this
    # volume and useless at real scale — traces are the most expensive signal
    # per event. ParentBased means a sampling decision made upstream is
    # honoured, so a single request is never traced in one service and dropped
    # in the next, which would produce broken half-traces.
    sampler = ParentBased(root=TraceIdRatioBased(settings.trace_sample_ratio))

    provider = TracerProvider(resource=resource, sampler=sampler)
    provider.add_span_processor(
        # Batched, not simple: a synchronous export on every span would add
        # network latency to every request it is supposed to be measuring.
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{settings.otlp_endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(
        app,
        # These produce no useful traces and would drown the interesting ones.
        excluded_urls="health,ready,metrics",
    )
    SQLAlchemyInstrumentor().instrument(engine=engine)

    logger.info("tracing enabled endpoint=%s ratio=%s", settings.otlp_endpoint, sampler)


def configure_metrics(app: FastAPI) -> None:
    """Expose Prometheus metrics at /metrics.

    The instrumentator provides the RED metrics — request rate, error rate, and
    a duration histogram. The histogram is what makes p95/p99 possible; a plain
    average hides exactly the tail latency users actually notice.
    """
    Instrumentator(
        should_group_status_codes=False,
        # Group /{code} into one series rather than one per short code. Without
        # this, the redirect path alone would create unbounded cardinality — the
        # single most common way to take down a Prometheus.
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics", "/health", "/ready"],
        inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
