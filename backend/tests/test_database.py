from contextlib import nullcontext
from unittest.mock import MagicMock

from sqlalchemy.exc import SQLAlchemyError

from app.database import ensure_fineli_search_indexes


def test_fineli_search_indexes_are_skipped_for_sqlite() -> None:
    engine = MagicMock()
    engine.dialect.name = "sqlite"

    ensure_fineli_search_indexes(engine)

    engine.begin.assert_not_called()


def test_fineli_search_indexes_are_created_for_postgresql() -> None:
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    connection = MagicMock()
    engine.begin.return_value = nullcontext(connection)

    ensure_fineli_search_indexes(engine)

    assert connection.execute.call_count == 3


def test_fineli_search_indexes_log_postgresql_fallback(
    caplog,
) -> None:
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    engine.begin.side_effect = SQLAlchemyError("permission denied")

    ensure_fineli_search_indexes(engine)

    assert "falling back to ILIKE" in caplog.text
