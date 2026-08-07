"""ORM models.

One table. The interesting decisions are the indexes and the fact that a link
is immutable once created — which is what makes the in-process cache in
`app/cache.py` correct rather than a source of stale reads.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Link(Base):
    __tablename__ = "links"

    # BigInteger everywhere except SQLite, which only autoincrements a column
    # declared exactly INTEGER PRIMARY KEY — a BIGINT primary key there is not
    # an alias for the rowid, so inserts come back with a NULL id and fail the
    # NOT NULL constraint. Postgres has no such quirk. This is the canonical
    # example of why the test suite runs against both engines: the SQLite-only
    # run would have hidden nothing here, but a Postgres-only run would have
    # hidden it completely.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )

    # The public short code. Unique + indexed because the redirect path looks
    # up by this column on every single request — it is the hot query, and an
    # unindexed lookup here is exactly the kind of thing we will deliberately
    # reintroduce later to demonstrate tracing catching it.
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)

    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Denormalised counter. Incrementing it on the redirect path is a write on
    # what would otherwise be a read-only request, which is a real trade-off:
    # it makes stats cheap to read and redirects marginally more expensive.
    hit_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Link code={self.code!r} hits={self.hit_count}>"
