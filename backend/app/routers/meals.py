from fastapi import APIRouter, HTTPException, Query

from app.integrations.fineli.client import ExternalProviderError
from app.integrations.themealdb.client import TheMealDbClient

router = APIRouter(prefix="/meals", tags=["meals"])


@router.get("/search")
def search_meals(q: str = Query(min_length=1, max_length=100)):
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Search query cannot be blank")

    client = TheMealDbClient()
    try:
        meals = client.search(query)
    except ExternalProviderError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "external_provider_unavailable", "message": "External recipe provider unavailable"},
        ) from exc
    finally:
        client.close()

    return [
        {
            "id": meal["external_id"],
            "name": meal["name"],
            "category": meal["category"],
            "area": meal["area"],
            "instructions": meal["instructions"],
            "imageUrl": meal["thumbnail_url"],
            "tags": meal["tags"],
            "youtubeUrl": meal["youtube_url"],
            "sourceUrl": meal["source_url"],
            "creativeCommonsConfirmed": meal["creative_commons_confirmed"],
            "ingredients": [
                {"name": ingredient["name"], "measure": ingredient["amount"] or None}
                for ingredient in meal["ingredients"]
            ],
        }
        for meal in meals
    ]
