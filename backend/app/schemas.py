"""Request and response models.

Pydantic validates at the boundary so nothing downstream has to re-check. The
URL validation here is also a small security control: it is what stops someone
storing a `javascript:` payload and turning your redirector into an XSS vector.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class LinkCreate(BaseModel):
    # HttpUrl accepts only http/https schemes, which is the point — an open
    # redirector that will emit any scheme you hand it is a genuine finding.
    target_url: HttpUrl
    custom_code: Annotated[str, Field(min_length=3, max_length=16)] | None = None

    @field_validator("custom_code")
    @classmethod
    def code_is_url_safe(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.isalnum():
            raise ValueError("custom_code must be alphanumeric")
        return v


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    short_url: str
    target_url: str
    created_at: datetime
    hit_count: int
    last_hit_at: datetime | None


class HealthOut(BaseModel):
    status: Literal["ok"]


class ReadyOut(BaseModel):
    status: Literal["ready", "degraded"]
    database: Literal["up", "down"]


class VersionOut(BaseModel):
    version: str
    git_sha: str
    # Which pod answered. This is what makes a rolling update visible in the
    # browser during a demo rather than something you have to take on faith.
    hostname: str


class ErrorOut(BaseModel):
    detail: str
