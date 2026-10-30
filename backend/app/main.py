from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.config import settings
from app.database import Base, engine
from app.routers import recipes


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Starter shortcut: create tables on startup.
    # Once the schema starts changing, switch to Alembic migrations.
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


@app.get("/api/health")
def health():
    return {"status": "ok"}
