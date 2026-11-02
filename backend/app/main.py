from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.config import settings
from app.database import Base, engine
from app.routers import recipes
from app.routers import external_recipes, ingredients, nutrition


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Create missing tables automatically for local development.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Recipe API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recipes.router, prefix="/api")
app.include_router(ingredients.router, prefix="/api")
app.include_router(nutrition.router, prefix="/api")
app.include_router(external_recipes.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
