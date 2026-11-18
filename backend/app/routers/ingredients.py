from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.integrations.fineli.factory import get_fineli_client
from app.integrations.fineli.matching import (
    candidate_rank,
    lookup_mapping,
    suggestion_queries,
)
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


@router.get("/suggestions", response_model=list[schemas.FineliFood])
def suggest_ingredients(
    query: str = Query(alias="q", min_length=1, max_length=100),
    db: Session = Depends(get_db),
):
    queries = suggestion_queries(query)
    if not queries:
        raise HTTPException(status_code=422, detail="Ingredient query cannot be blank")
    client = get_fineli_client(db)
    try:
        candidates_by_id = {}
        mapped_id: str | None = None
        mapping = lookup_mapping(db, query)
        if mapping and mapping.get("fineli_id"):
            try:
                mapped_food = client.get_food(str(mapping["fineli_id"]))
                candidates_by_id[mapped_food["id"]] = mapped_food
                mapped_id = mapped_food["id"]
            except FineliFoodNotFound:
                pass
        for search_term in queries:
            for food in client.search_foods(search_term):
                candidates_by_id.setdefault(food["id"], food)
        search_term = queries[0]
        ranked = sorted(
            candidates_by_id.values(),
            key=lambda food: (
                0 if food["id"] == mapped_id else 1,
                candidate_rank(food, search_term),
            ),
        )
        return ranked[:5]
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
