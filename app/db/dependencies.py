from typing import AsyncGenerator
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Inyector de dependencia para sesiones de base de datos por petición."""
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de base de datos no configurado o no disponible.",
        )

    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
