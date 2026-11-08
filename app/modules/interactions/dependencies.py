from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.dependencies import get_db_session
from app.modules.interactions.service import ReviewService


def get_review_service(
    session: AsyncSession = Depends(get_db_session),
) -> ReviewService:
    """Provee una instancia de ReviewService con su sesión inyectada."""
    return ReviewService(session)
