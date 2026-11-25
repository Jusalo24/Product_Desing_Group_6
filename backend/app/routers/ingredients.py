from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.integrations.fineli.factory import get_fineli_client
from app.integrations.fineli.matching import (
    AUTO_MATCH_CONFIDENCES,
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
        results = client.search_foods(query)
        if len(results) >= 5 or any(ch in query for ch in ("%", "_")):
            return results
        candidates_by_id = {food["id"]: food for food in results}
        queries = suggestion_queries(query)
        for search_term in queries:
            for food in client.search_foods(search_term):
                candidates_by_id.setdefault(food["id"], food)
        if len(candidates_by_id) == len(results):
            return results
        rank_queries = [query, *[q for q in queries if q != query]]
        return sorted(
            candidates_by_id.values(),
            key=lambda food: candidate_rank(food, rank_queries),
        )[:20]
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
        if (
            mapping
            and mapping.get("fineli_id")
            and mapping.get("confidence") in AUTO_MATCH_CONFIDENCES
        ):
            try:
                mapped_food = client.get_food(str(mapping["fineli_id"]))
                candidates_by_id[mapped_food["id"]] = mapped_food
                mapped_id = mapped_food["id"]
            except FineliFoodNotFound:
                pass
        for search_term in queries:
            for food in client.search_foods(search_term):
                candidates_by_id.setdefault(food["id"], food)
        ranked = sorted(
            candidates_by_id.values(),
            key=lambda food: (
                0 if food["id"] == mapped_id else 1,
                candidate_rank(food, queries),
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
