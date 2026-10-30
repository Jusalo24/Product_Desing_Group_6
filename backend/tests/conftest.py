from collections.abc import Iterator
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Add the backend directory so pytest works from either the repo root or backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import database, main


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Provide an API client backed by a fresh in-memory SQLite database per test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_session = sessionmaker(bind=engine, autoflush=False)

    # Route database requests through the isolated test engine, not local PostgreSQL.
    def override_get_db():
        with test_session() as db:
            yield db

    # The lifespan creates tables using main.engine when TestClient starts the app.
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_db] = override_get_db

    try:
        with TestClient(main.app) as test_client:
            yield test_client
    finally:
        # Prevent dependency overrides and database connections leaking into other tests.
        main.app.dependency_overrides.pop(database.get_db, None)
        engine.dispose()
