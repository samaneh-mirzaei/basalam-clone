from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.core.config import settings


@lru_cache
def engine() -> Engine:
    return create_engine(settings().database_url.get_secret_value(), pool_pre_ping=True, hide_parameters=True)


def get_session() -> Iterator[Session]:
    with Session(engine()) as session:
        yield session
