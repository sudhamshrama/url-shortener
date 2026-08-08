"""ORM models.

One table. The interesting decisions are the indexes and the fact that a link
is immutable once created — which is what makes the in-process cache in
`app/cache.py` correct rather than a source of stale reads.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Link(Base):
    __tablename__ = "links"

    # The index is declared explicitly here rather than via `index=True` on the
    # column, so that the name matches the Alembic migration exactly.
    #
    # It did not, and CI caught it: `index=True` makes SQLAlchemy auto-generate
    # `ix_links_code`, while the migration creates `ux_links_code`. Tests build
    # their schema from this model and got `ix_`; production builds it from the
    # migration and gets `ux_`. Any code keying off the constraint name is then
    # correct in exactly one of the two environments.
    __table_args__ = (Index("ux_links_code", "code", unique=True),)

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

    # The public short code. The unique index is declared in __table_args__
    # above — the redirect path looks up by this column on every request, so it
    # is the hot query and an unindexed lookup here would be a real problem.
    code: Mapped[str] = mapped_column(String(16), nullable=False)

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
