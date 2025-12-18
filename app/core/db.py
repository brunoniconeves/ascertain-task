from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import Request
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


def _create_naming_convention() -> dict[str, str]:
    return {
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }


metadata_obj = MetaData(naming_convention=_create_naming_convention())


class Base(DeclarativeBase):
    metadata = metadata_obj


def create_engine(*, database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def create_sessionmaker(*, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def init_db(*, app: Any, database_url: str) -> None:
    engine = create_engine(database_url=database_url)
    app.state.db_engine = engine
    app.state.db_sessionmaker = create_sessionmaker(engine=engine)


async def close_db(*, app: Any) -> None:
    engine: AsyncEngine | None = getattr(app.state, "db_engine", None)
    if engine is None:
        return
    await engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.db_sessionmaker
    async with sessionmaker() as session:
        yield session
