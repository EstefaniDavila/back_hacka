"""Componentes y utilidades compartidas de VeciRed IA."""
from .pagination import PageMeta, PaginatedResponse
from .repository import BaseRepository

__all__ = ["BaseRepository", "PageMeta", "PaginatedResponse"]
