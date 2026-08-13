"""Link creation, lookup, and redirect."""

import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.cache import LRUCache
from app.deps import AppSettings, DbSession
from app.models import Link
from app.observability import (
    cache_hit_ratio,
    cache_size,
    links_created_total,
    redirect_misses_total,
    redirects_total,
)
from app.schemas import LinkCreate, LinkOut
from app.shortcode import generate_code

logger = logging.getLogger(__name__)

router = APIRouter()

# Populated by main.py at startup so the cache lives for the process lifetime
# rather than being rebuilt per request.
cache: LRUCache = LRUCache(maxsize=1024)


def _is_code_conflict(exc: IntegrityError) -> bool:
    """Distinguish "that short code is taken" from every other integrity error.

    This matters more than it looks. An earlier version of this file treated
    *any* IntegrityError as a collision, which meant a NOT NULL violation on a
    different column was silently retried five times and then reported as a
    keyspace exhaustion problem — a completely wrong diagnosis, with logs that
    actively pointed away from the real cause.

    The first version of this matched the literal string "ux_links_code" in the
    error text, and CI caught the flaw: the tests built their schema from the
    ORM model, which auto-named the index `ix_links_code`, so the match failed
    and a 500 escaped where a 409 belonged. Matching on a hardcoded name is
    brittle even once the names agree.

    So: prefer psycopg's structured diagnostics, which report the violated
    constraint as data rather than prose, and fall back to text matching only
    for engines that do not provide them (SQLite).
    """
    orig = getattr(exc, "orig", None)

    # psycopg3 exposes the constraint name directly. No parsing, no locale
    # dependence, no breakage when a name changes.
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)
    if constraint:
        return "code" in constraint

    # SQLite reports "UNIQUE constraint failed: links.code" and offers nothing
    # structured, so text matching is the only option there.
    message = str(orig or exc).lower()
    return "unique" in message and "code" in message


def _to_out(link: Link, base_url: str) -> LinkOut:
    return LinkOut(
        code=link.code,
        short_url=f"{base_url.rstrip('/')}/{link.code}",
        target_url=link.target_url,
        created_at=link.created_at,
        hit_count=link.hit_count,
        last_hit_at=link.last_hit_at,
    )


@router.post(
    "/api/links",
    response_model=LinkOut,
    status_code=status.HTTP_201_CREATED,
    tags=["links"],
)
def create_link(
    payload: LinkCreate,
    db: DbSession,
    settings: AppSettings,
) -> LinkOut:
    """Create a short link.

    Collision handling is done by letting the database's unique constraint
    reject duplicates and retrying, rather than by SELECTing first to check
    availability. A check-then-insert has a race window between the two
    statements; under concurrency two requests both see "available" and one
    insert fails anyway. Relying on the constraint is the only correct version.
    """
    target = str(payload.target_url)

    if payload.custom_code:
        link = Link(code=payload.custom_code, target_url=target)
        db.add(link)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            if not _is_code_conflict(exc):
                raise
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"code '{payload.custom_code}' is already taken",
            ) from None
        db.refresh(link)
        cache.put(link.code, link.target_url)
        links_created_total.labels(code_type="custom").inc()
        return _to_out(link, settings.base_url)

    for attempt in range(settings.shortcode_max_attempts):
        code = generate_code(settings.shortcode_length)
        link = Link(code=code, target_url=target)
        db.add(link)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            # Anything that is not a code collision is a real fault. Retrying it
            # would waste attempts and bury the actual cause.
            if not _is_code_conflict(exc):
                raise
            logger.warning("shortcode collision on %r (attempt %d)", code, attempt + 1)
            continue
        db.refresh(link)
        cache.put(link.code, link.target_url)
        links_created_total.labels(code_type="generated").inc()
        return _to_out(link, settings.base_url)

    # Exhausting retries means the keyspace is saturated, not that we were
    # unlucky. That is a capacity problem and deserves a 500, loudly.
    logger.error("exhausted %d shortcode attempts", settings.shortcode_max_attempts)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="could not allocate a short code",
    )


@router.get("/api/links/{code}", response_model=LinkOut, tags=["links"])
def get_link(
    code: str,
    db: DbSession,
    settings: AppSettings,
) -> LinkOut:
    """Stats for a link. Deliberately not cached — hit_count changes constantly."""
    link = db.scalar(select(Link).where(Link.code == code))
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown code")
    return _to_out(link, settings.base_url)


# NOTE: this route must be registered LAST. FastAPI matches routes in
# registration order, and "/{code}" would otherwise swallow "/health",
# "/version", and every other single-segment path.
@router.get("/{code}", tags=["links"], include_in_schema=False)
def redirect(code: str, db: DbSession) -> RedirectResponse:
    """The hot path. Resolve a code and redirect."""
    target = cache.get(code)

    if target is None:
        link = db.scalar(select(Link).where(Link.code == code))
        if link is None:
            redirect_misses_total.inc()
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown code")
        target = link.target_url
        cache.put(code, target)
        redirects_total.labels(cache="miss").inc()
    else:
        redirects_total.labels(cache="hit").inc()

    # Gauges are sampled at scrape time, so setting them on the hot path is
    # cheap and keeps them current without a background thread.
    cache_size.set(cache.size)
    cache_hit_ratio.set(cache.hit_rate)

    # Counter bump as a single UPDATE rather than read-modify-write, so
    # concurrent redirects to the same link cannot lose increments.
    #
    # `func.now()` is the *database's* clock, not the application's — so the
    # value is consistent regardless of which pod served the request or how
    # badly a node's NTP has drifted.
    db.execute(
        update(Link)
        .where(Link.code == code)
        .values(hit_count=Link.hit_count + 1, last_hit_at=func.now())
    )
    db.commit()

    # 307 rather than 301: a permanent redirect gets cached by the browser
    # forever, which means repeat visits never reach us and hit_count silently
    # stops counting. Correctness of the metric beats the marginal latency win.
    return RedirectResponse(url=target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
