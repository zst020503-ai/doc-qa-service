from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "doc-qa-service"
    database_url: str = "postgresql+psycopg2://docqa:docqa@db:5432/docqa"

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 720

    embedding_provider: str = "mock"
    embedding_dim: int = 1536
    embedding_model: str = "text-embedding-3-small"

    llm_provider: str = "mock"
    chat_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""

    retrieve_top_k: int = 5
    answer_threshold: float = 0.20

    chunk_size: int = 300
    chunk_overlap: int = 50
    upload_dir: str = "/data/uploads"
    max_upload_mb: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
