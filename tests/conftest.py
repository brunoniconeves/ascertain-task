from __future__ import annotations

import asyncio
import os

import pytest

from app.core.db import Base, create_engine


@pytest.fixture()
def database_url(tmp_path) -> str:
    db_file = tmp_path / "test.sqlite3"
    return f"sqlite+aiosqlite:///{db_file}"


@pytest.fixture(autouse=True)
def _set_test_database_url(database_url: str) -> None:
    os.environ["DATABASE_URL"] = database_url
    # Settings are cached via @lru_cache; clear so each test can use its own DB URL.
    from app.core.settings import get_settings

    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _create_test_schema(database_url: str) -> None:
    async def run() -> None:
        # Ensure all model modules are imported so Base.metadata is populated.
        from app.patients import models as _patients_models  # noqa: F401
        from app.patients.notes import models as _patient_notes_models  # noqa: F401

        engine = create_engine(database_url=database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(run())


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c
