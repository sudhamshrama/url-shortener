"""Health, readiness, and version endpoints.

The distinction between `/health` and `/ready` is the single most important
thing in this file:

  /health  -> LIVENESS.  "Is this process wedged?"  Kubernetes RESTARTS the pod
              when this fails. It must therefore check *nothing external*.
              If liveness checked the database, a brief Postgres blip would
              fail the probe on every replica at once and Kubernetes would
              restart the entire fleet — turning a recoverable dependency
              wobble into a self-inflicted outage. This is a real and common
              production incident.

  /ready   -> READINESS.  "Should this pod receive traffic right now?"
              Kubernetes removes the pod from the Service endpoints when this
              fails, but does not restart it. Checking the database here is
              correct: no database means we cannot serve, but we will recover
              on our own once it returns.
"""

import socket

from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.deps import AppSettings, DbSession
from app.schemas import HealthOut, ReadyOut, VersionOut

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    """Liveness. Intentionally checks nothing but its own ability to respond."""
    return HealthOut(status="ok")


@router.get("/ready", response_model=ReadyOut)
def ready(response: Response, db: DbSession) -> ReadyOut:
    """Readiness. Verifies the database is actually reachable."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # 503 so Kubernetes pulls this pod out of rotation. We do not raise,
        # because a structured body is more useful than a stack trace when
        # someone curls this during an incident.
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyOut(status="degraded", database="down")
    return ReadyOut(status="ready", database="up")


@router.get("/version", response_model=VersionOut)
def version(settings: AppSettings) -> VersionOut:
    """Which build, and which pod, is answering.

    `hostname` is the pod name inside Kubernetes. Surfacing it is what lets the
    frontend visibly prove a rolling update is in progress — you watch the
    version flip while requests keep succeeding.
    """
    return VersionOut(
        version=settings.app_version,
        git_sha=settings.git_sha,
        hostname=socket.gethostname(),
    )
