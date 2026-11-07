from typing import Any, Dict, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from app.core.logging import logger


class VeciRedException(Exception):
    """Excepción base para el dominio de VeciRed IA."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class DatabaseConnectionException(VeciRedException):
    """Lanzada cuando existe un fallo en la conexión con la base de datos."""

    def __init__(self, message: str = "Error de conexión con PostgreSQL"):
        super().__init__(
            message=message,
            code="DATABASE_CONNECTION_ERROR",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class EntityNotFoundException(VeciRedException):
    """Lanzada cuando una entidad solicitada no existe."""

    def __init__(self, entity_name: str, identifier: Any):
        super().__init__(
            message=f"{entity_name} con identificador {identifier} no existe.",
            code="ENTITY_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


async def vecired_exception_handler(
    request: Request, exc: VeciRedException
) -> JSONResponse:
    """Captura excepciones de negocio de VeciRed."""
    logger.error(
        "VeciRedException: code=%s message=%s path=%s",
        exc.code,
        exc.message,
        request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Captura errores no controlados protegiendo detalles internos."""
    logger.exception("Excepción no controlada en %s: %s", request.url.path, str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "code": "INTERNAL_SERVER_ERROR",
            "message": "Ha ocurrido un error inesperado en el servidor.",
            "details": {},
        },
    )
