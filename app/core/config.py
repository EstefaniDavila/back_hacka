import re
from functools import lru_cache
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración centralizada de la aplicación con Pydantic v2."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "VeciRed IA Backend"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    # Supabase Auth
    SUPABASE_URL: str = "https://gipoemmdfoxbcrsjtkrj.supabase.co"
    SUPABASE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""

    # PostgreSQL / Supabase
    DATABASE_URL: str = ""
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Union[str, None]) -> str:
        """Garantiza que el esquema use el driver asyncpg y soporte IPv4 de Supabase."""
        if not v or not isinstance(v, str) or v.strip() == "":
            return ""
        clean_url = v.strip()
        if clean_url.startswith("postgresql://"):
            clean_url = clean_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif clean_url.startswith("postgres://"):
            clean_url = clean_url.replace("postgres://", "postgresql+asyncpg://", 1)

        # Si el usuario configura la conexión directa de Supabase (db.<ref>.supabase.co),
        # adaptar automáticamente al Pooler IPv4 para evitar el error de red IPv6 en WSL / Docker
        supabase_match = re.search(r"@db\.([a-z0-9]+)\.supabase\.co", clean_url)
        if supabase_match:
            project_ref = supabase_match.group(1)
            clean_url = re.sub(
                r"://postgres:([^@]+)@db\.[a-z0-9]+\.supabase\.co(?::[0-9]+)?",
                rf"://postgres.{project_ref}:\1@aws-0-us-east-1.pooler.supabase.com:6543",
                clean_url,
            )

        return clean_url


@lru_cache
def get_settings() -> Settings:
    """Retorna una instancia única en caché de la configuración."""
    return Settings()


settings = get_settings()
