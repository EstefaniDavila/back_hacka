from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.exceptions import (
    VeciRedException,
    unhandled_exception_handler,
    vecired_exception_handler,
)
from app.core.health import router as health_router
from app.core.logging import logger, setup_logging
from app.db.session import close_db_connection
from app.modules.geo.router import router as geo_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Control del ciclo de vida de la aplicación."""
    setup_logging()
    logger.info("Iniciando %s v%s...", settings.PROJECT_NAME, settings.VERSION)
    yield
    logger.info("Deteniendo %s...", settings.PROJECT_NAME)
    await close_db_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend de VeciRed IA: Economía local, solidaridad y emergencias.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Manejo centralizado de excepciones
app.add_exception_handler(VeciRedException, vecired_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Rutas API v1
app.include_router(health_router, prefix=settings.API_V1_STR)
app.include_router(geo_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Root"])
async def root():
    """Ruta raíz de bienvenida e información de la API."""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health",
    }
