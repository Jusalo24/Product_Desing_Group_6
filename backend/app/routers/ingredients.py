from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.integrations.fineli.factory import get_fineli_client
from app.integrations.fineli.local_client import FineliFoodNotFound
from app.integrations.fineli.matching import (
    AUTO_MATCH_CONFIDENCES,
    candidate_rank,
    lookup_mapping,
    suggestion_queries,
)

router = APIRouter(prefix="/ingredients", tags=["ingredients"])


@router.get("/search", response_model=list[schemas.FineliFood])
def search_ingredients(
    query: str = Query(alias="q", min_length=1, max_length=100),
    limit: int = Query(default=20, ge=1, le=20),
    db: Session = Depends(get_db),
):
    cleaned = query.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="Ingredient query cannot be blank")

    client = get_fineli_client(db)
    try:
        if any(ch in cleaned for ch in ("%", "_")):
            return client.search_foods(cleaned)[:limit]

        candidates_by_id: dict[str, dict] = {}
        mapped_id: str | None = None
        mapping = lookup_mapping(db, cleaned)
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

        queries = suggestion_queries(cleaned)
        search_terms = [cleaned, *[term for term in queries if term != cleaned]]
        for search_term in search_terms:
            for food in client.search_foods(search_term):
                candidates_by_id.setdefault(food["id"], food)

        ranked = sorted(
            candidates_by_id.values(),
            key=lambda food: (
                0 if food["id"] == mapped_id else 1,
                candidate_rank(food, search_terms),
            ),
        )
        return ranked[:limit]
    finally:
        client.close()
