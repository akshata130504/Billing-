import json
from pathlib import Path
from typing import Annotated, List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Resolve .env files relative to the repository layout instead of the current
# working directory so the backend behaves the same regardless of where
# uvicorn/pytest/alembic are launched from.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    PROJECT_NAME: str = "Rooman Billing"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    SECRET_KEY: str = "phase0-development-secret-key-replace-in-production-12345"

    # NoDecode stops pydantic-settings from JSON-decoding the raw env value so the
    # validator below can accept either a JSON array or a comma-separated list.
    ALLOWED_ORIGINS: Annotated[List[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            value = v.strip()
            if value.startswith("["):
                return json.loads(value)
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return v

    # PostgreSQL Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "rooman_billing"

    DATABASE_URL: str | None = None

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Later files take precedence: backend/.env overrides the repo-root .env.
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
