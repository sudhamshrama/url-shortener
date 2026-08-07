"""Shared dependency aliases.

Using `Annotated[X, Depends(...)]` rather than `x: X = Depends(...)` is the
current FastAPI idiom. Two concrete reasons beyond style:

  * A mutable-ish call in a default argument is evaluated once at import time,
    which is the classic Python footgun (flake8-bugbear's B008 flags it). The
    Annotated form sidesteps the argument-default mechanism entirely.
  * The alias is reusable, so the dependency is declared once here instead of
    being repeated — and correctly typed — in every handler signature.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
