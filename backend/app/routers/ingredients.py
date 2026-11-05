from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.integrations.fineli.factory import get_fineli_client
from app.integrations.fineli.local_client import FineliFoodNotFound

router = APIRouter(prefix="/ingredients", tags=["ingredients"])


@router.get("/search", response_model=list[schemas.FineliFood])
def search_ingredients(
    query: str = Query(alias="q", min_length=1, max_length=100),
    db: Session = Depends(get_db),
):
    client = get_fineli_client(db)
    try:
        return client.search_foods(query)
    finally:
        client.close()


@router.get("/{food_id}", response_model=schemas.FineliFood)
def get_ingredient(food_id: str, db: Session = Depends(get_db)):
    client = get_fineli_client(db)
    try:
        return client.get_food(food_id)
    except FineliFoodNotFound as exc:
        raise HTTPException(404, "Fineli food not found") from exc
    finally:
        client.close()
