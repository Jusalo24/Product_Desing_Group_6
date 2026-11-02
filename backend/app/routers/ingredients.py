from fastapi import APIRouter, HTTPException, Query

from app import schemas
from app.integrations.fineli.client import ExternalProviderError, FineliClient

router = APIRouter(prefix="/ingredients", tags=["ingredients"])


@router.get("/search", response_model=list[schemas.FineliFood])
def search_ingredients(query: str = Query(alias="q", min_length=1, max_length=100)):
    client = FineliClient()
    try:
        return client.search_foods(query)
    except ExternalProviderError as exc:
        raise HTTPException(502, "Fineli unavailable") from exc
    finally:
        client.close()


@router.get("/{food_id}", response_model=schemas.FineliFood)
def get_ingredient(food_id: str):
    client = FineliClient()
    try:
        return client.get_food(food_id)
    except ExternalProviderError as exc:
        raise HTTPException(502, "Fineli unavailable") from exc
    finally:
        client.close()
