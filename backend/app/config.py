from os import environ

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://recipes:recipes@localhost:5432/recipes"
    cors_origins: list[str] = ["http://localhost:5173"]
    fineli_api_base_url: str = environ.get("FINELI_API_BASE_URL", "https://fineli.fi/fineli/api/v1")
    fineli_foods_path: str = environ.get("FINELI_FOODS_PATH", "foods")
    themealdb_api_base_url: str = environ.get("THEMEALDB_API_BASE_URL", "https://www.themealdb.com/api/json/v1")
    themealdb_api_key: str = "1"
    external_api_timeout_seconds: float = 10.0
    external_cache_ttl_seconds: int = 3600
    external_cache_max_size: int = 100

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
