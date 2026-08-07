"""Deliberate failure injection.

These endpoints exist so that Stage 6's dashboards, alert rules, and traces can
be *proven* to work rather than assumed to work. An observability stack that has
never seen a real incident is decoration.

Every one of these is gated behind ENABLE_DEBUG_ENDPOINTS, which is false by
default and enabled only in the dev overlay. Shipping a reachable /debug/leak to
production would be a genuine denial-of-service vector — the gate is the point,
not a formality.
"""

import logging
import time

from fastapi import APIRouter, HTTPException, Query, status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug", tags=["debug"])

# Module-level so the allocated memory is never garbage collected — that is what
# makes it a genuine leak rather than a brief spike.
_ballast: list[bytes] = []


@router.get("/slow")
def slow(seconds: float = Query(default=2.0, ge=0, le=30)) -> dict[str, float]:
    """Burn wall-clock time to push p95/p99 latency up.

    Uses a real sleep rather than a busy loop so it produces latency without
    also producing CPU saturation — the two look very different on a dashboard
    and we want to be able to demonstrate each independently.
    """
    logger.warning("debug: sleeping %.2fs to inflate latency", seconds)
    time.sleep(seconds)
    return {"slept_seconds": seconds}


@router.get("/error")
def error(rate: float = Query(default=1.0, ge=0, le=1)) -> dict[str, str]:
    """Return 500s at a configurable rate, to drive an error-rate alert.

    A rate below 1.0 is the more interesting demo: a partial failure is what
    alert thresholds are actually tuned for, and it shows whether your rule
    fires on a 5% error rate or only on total outage.
    """
    import secrets

    if secrets.SystemRandom().random() < rate:
        logger.error("debug: deliberate 500 (rate=%.2f)", rate)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="deliberate failure for observability testing",
        )
    return {"status": "survived"}


@router.get("/leak")
def leak(megabytes: int = Query(default=50, ge=1, le=500)) -> dict[str, int]:
    """Allocate memory and never release it, to trigger an OOMKill.

    This is how we demonstrate that container memory limits are real, that
    Kubernetes restarts the pod when one is breached, and that the resulting
    CrashLoopBackOff is visible in both the dashboards and the logs.
    """
    _ballast.append(b"\0" * (megabytes * 1024 * 1024))
    total = sum(len(chunk) for chunk in _ballast) // (1024 * 1024)
    logger.warning("debug: leaked %dMB, %dMB held total", megabytes, total)
    return {"allocated_mb": megabytes, "total_held_mb": total}


@router.post("/leak/release")
def release() -> dict[str, str]:
    """Escape hatch, so a demo does not require restarting the pod."""
    _ballast.clear()
    return {"status": "released"}
