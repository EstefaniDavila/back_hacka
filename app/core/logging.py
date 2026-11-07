import logging
import sys
from app.core.config import settings


def setup_logging() -> None:
    """Configura el sistema de logging estándar de la aplicación."""
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    log_format = "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    # Reducir verbosidad de librerías externas
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DEBUG else logging.WARNING
    )


logger = logging.getLogger("vecired")
