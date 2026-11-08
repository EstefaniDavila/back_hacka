"""Módulo de interacciones (reseñas, valoraciones y favoritos) para VeciRed IA."""
from .models import Review, SavedItem
from .router import router as reviews_router

__all__ = [
    "Review",
    "SavedItem",
    "reviews_router",
]
