from datetime import datetime, timezone
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.db.session import check_db_health

router = APIRouter(tags=["Salud"])


@router.get("/health", summary="Verificación de estado de la aplicación")
async def health_check() -> JSONResponse:
    """Endpoint de salud del backend y estado del enlace a PostgreSQL."""
    db_ok, db_message = await check_db_health()

    if settings.DATABASE_URL:
        overall_status = "healthy" if db_ok else "degraded"
        status_code = status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        # Modo inicial sin DATABASE_URL provista todavía
        overall_status = "unconfigured_database"
        status_code = status.HTTP_200_OK

    payload = {
        "status": overall_status,
        "app": {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
        },
        "services": {
            "database": {
                "status": "connected" if db_ok else "disconnected",
                "message": db_message,
            }
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(status_code=status_code, content=payload)
