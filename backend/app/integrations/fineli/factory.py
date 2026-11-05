from __future__ import annotations

from sqlalchemy.orm import Session

from app.integrations.fineli.local_client import LocalFineliClient


def get_fineli_client(db: Session) -> LocalFineliClient:
    """Return the imported Fineli dataset client; nutrition lookups are offline."""
    return LocalFineliClient(db)
