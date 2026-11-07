from typing import Optional, Tuple
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.core.config import settings
from app.core.logging import logger

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> Optional[AsyncEngine]:
    """Crea u obtiene la instancia singleton del motor asíncrono de base de datos."""
    global _engine, _session_factory
    if not settings.DATABASE_URL:
        return None

    if _engine is None:
        # statement_cache_size=0 es imprescindible para PgBouncer/Supabase Pooler
        connect_args = {
            "prepared_statement_cache_size": 0,
            "statement_cache_size": 0,
        }
        _engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_pre_ping=True,
            connect_args=connect_args,
            echo=settings.DEBUG and settings.ENVIRONMENT == "development",
        )
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _engine


def get_session_factory() -> Optional[async_sessionmaker[AsyncSession]]:
    """Retorna la fábrica de sesiones asíncronas."""
    global _session_factory
    if _session_factory is None:
        get_engine()
    return _session_factory


async def close_db_connection() -> None:
    """Cierra el pool de conexiones de base de datos de manera ordenada."""
    global _engine, _session_factory
    if _engine is not None:
        logger.info("Cerrando pool de conexiones PostgreSQL...")
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Pool de conexiones cerrado.")


async def check_db_health() -> Tuple[bool, str]:
    """Verifica la conectividad real con PostgreSQL sin exponer credenciales."""
    if not settings.DATABASE_URL:
        return False, "DATABASE_URL no está configurada en .env"

    factory = get_session_factory()
    if factory is None:
        return False, "No fue posible inicializar el motor de base de datos"

    try:
        async with factory() as session:
            result = await session.execute(text("SELECT 1"))
            if result.scalar() == 1:
                return True, "Conexión con PostgreSQL exitosa"
            return False, "Respuesta inesperada desde PostgreSQL"
    except Exception as exc:
        logger.warning("Fallo en verificación de PostgreSQL: %s", str(exc))
        return False, f"Fallo de conexión ({exc.__class__.__name__})"
