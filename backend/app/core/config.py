from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List, Union


class Settings(BaseSettings):
    # Project
    PROJECT_NAME: str = "Legislative Redline Tool"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Application-specific settings
    DOCUMENT_RETENTION_HOURS: int = 24
    STATUTE_CACHE_DAYS: int = 7
    MAX_UPLOAD_SIZE_MB: int = 50

    # CORS
    BACKEND_CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5176",
        "http://redline.localhost",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # Database
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "localdev"
    POSTGRES_SERVER: str = "db"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "redline_db"

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Sync URL for Alembic migrations"""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # External APIs
    GOVINFO_API_KEY: str = ""  # Free from api.data.gov

    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production"

    # Upload directory
    UPLOAD_DIR: str = "/app/uploads"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
