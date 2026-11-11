"""Rutas de API v1 para el motor de búsqueda inteligente geolocalizada de VeciRed IA."""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status

from app.core.security import CurrentUser, get_current_user, get_optional_current_user
from app.modules.search.dependencies import get_search_service
from app.modules.search.schemas import (
    GlobalSearchResponse,
    PaginatedEmergenciesSearch,
    PaginatedProductsSearch,
    PaginatedServicesSearch,
    PaginatedSolidaritySearch,
    SearchSort,
)
from app.modules.search.service import SearchService

router = APIRouter(prefix="/search", tags=["Búsqueda Inteligente Geolocalizada"])


# ----------------------------------------------------------------------
# 1. BÚSQUEDA GENERAL TRANSVERSAL
# ----------------------------------------------------------------------
@router.get(
    "",
    response_model=GlobalSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Búsqueda global inteligente y geolocalizada en VeciRed",
)
async def search_all(
    q: Optional[str] = Query(None, description="Texto libre a buscar (oficio, producto, ayuda, emergencia)"),
    latitude: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Latitud GPS del usuario"),
    longitude: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Longitud GPS del usuario"),
    radius_km: Optional[float] = Query(None, description="Radio barrial en km: 1, 3, 5, 10 o null para toda la comunidad"),
    community_id: Optional[uuid.UUID] = Query(None, description="Filtrar por comunidad vecinal específica"),
    sort: SearchSort = Query(SearchSort.RECOMMENDED, description="Criterio de ordenación: relevance, distance, recommended"),
    page: int = Query(1, ge=1, description="Página actual"),
    page_size: int = Query(20, ge=1, le=100, description="Cantidad de resultados por página"),
    include_emergencies: bool = Query(True, description="Incluir emergencias en los resultados consolidados"),
    modules: Optional[str] = Query(None, description="Módulos a incluir separados por comas: services,products,solidarity,emergencies"),
    current_user: Optional[CurrentUser] = Depends(get_optional_current_user),
    service: SearchService = Depends(get_search_service),
):
    """
    Motor transversal de búsqueda barrial inteligente:
    - Evalúa similitud de texto, categorías y sinónimos contextuales.
    - Calcula distancias reales usando coordenadas de `addresses` (Haversine).
    - Aplica ranking multidimensional: Coincidencia (40%), Cercanía (25%), Reputación bayesiana (25%), Experiencia (10%).
    - No penaliza a vecinos nuevos e integra recomendaciones precalculadas.
    """
    return await service.search_all(
        query=q,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        community_id=community_id,
        sort=sort,
        page=page,
        page_size=page_size,
        user_id=current_user.id if current_user else None,
        include_emergencies=include_emergencies,
        modules=modules,
    )


# ----------------------------------------------------------------------
# 2. BÚSQUEDA DE SERVICIOS
# ----------------------------------------------------------------------
@router.get(
    "/services",
    response_model=PaginatedServicesSearch,
    status_code=status.HTTP_200_OK,
    summary="Búsqueda geolocalizada de servicios y oficios",
)
async def search_services(
    q: Optional[str] = Query(None, description="Oficio, habilidad o servicio (ej: gasfitero, electricista)"),
    latitude: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Latitud del usuario"),
    longitude: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Longitud del usuario"),
    radius_km: Optional[float] = Query(None, description="Radio máximo en km (1, 3, 5, 10 o null)"),
    category_id: Optional[uuid.UUID] = Query(None, description="Filtrar por categoría"),
    community_id: Optional[uuid.UUID] = Query(None, description="Filtrar por comunidad"),
    sort: SearchSort = Query(SearchSort.RECOMMENDED, description="relevance, distance, recommended"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Optional[CurrentUser] = Depends(get_optional_current_user),
    service: SearchService = Depends(get_search_service),
):
    """
    Retorna servicios ordenados por coincidencia, proximidad, reputación bayesiana
    y experiencia comprobada del prestador.
    """
    return await service.search_services(
        query=q,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        category_id=category_id,
        community_id=community_id,
        sort=sort,
        page=page,
        page_size=page_size,
        user_id=current_user.id if current_user else None,
    )


# ----------------------------------------------------------------------
# 3. BÚSQUEDA DE PRODUCTOS
# ----------------------------------------------------------------------
@router.get(
    "/products",
    response_model=PaginatedProductsSearch,
    status_code=status.HTTP_200_OK,
    summary="Búsqueda geolocalizada de productos locales",
)
async def search_products(
    q: Optional[str] = Query(None, description="Nombre de producto o negocio (ej: pan, torta, abarrotes)"),
    latitude: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Latitud del usuario"),
    longitude: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Longitud del usuario"),
    radius_km: Optional[float] = Query(None, description="Radio máximo en km"),
    category_id: Optional[uuid.UUID] = Query(None, description="Filtrar por categoría de producto"),
    community_id: Optional[uuid.UUID] = Query(None, description="Filtrar por comunidad"),
    sort: SearchSort = Query(SearchSort.RECOMMENDED, description="relevance, distance, recommended"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Optional[CurrentUser] = Depends(get_optional_current_user),
    service: SearchService = Depends(get_search_service),
):
    """
    Retorna productos locales ordenados por relevancia, cercanía de la tienda
    y reputación comercial del negocio.
    """
    return await service.search_products(
        query=q,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        category_id=category_id,
        community_id=community_id,
        sort=sort,
        page=page,
        page_size=page_size,
        user_id=current_user.id if current_user else None,
    )


# ----------------------------------------------------------------------
# 4. BÚSQUEDA DE AYUDA SOLIDARIA
# ----------------------------------------------------------------------
@router.get(
    "/solidarity",
    response_model=PaginatedSolidaritySearch,
    status_code=status.HTTP_200_OK,
    summary="Búsqueda geolocalizada en el muro solidario",
)
async def search_solidarity(
    q: Optional[str] = Query(None, description="Palabra clave en el muro solidario (ej: taladro, apoyo escolar)"),
    latitude: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Latitud del usuario"),
    longitude: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Longitud del usuario"),
    radius_km: Optional[float] = Query(None, description="Radio máximo en km"),
    post_type: Optional[str] = Query(None, description="request, offer, donation, exchange"),
    community_id: Optional[uuid.UUID] = Query(None, description="Filtrar por comunidad"),
    sort: SearchSort = Query(SearchSort.RECOMMENDED, description="relevance, distance, recommended"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Optional[CurrentUser] = Depends(get_optional_current_user),
    service: SearchService = Depends(get_search_service),
):
    """
    Retorna publicaciones solidarias. Prioriza necesidades urgentes y cercanía.
    No utiliza estrellas de calificación para ordenar pedidos de auxilio vecinal.
    """
    return await service.search_solidarity(
        query=q,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        post_type=post_type,
        community_id=community_id,
        sort=sort,
        page=page,
        page_size=page_size,
        user_id=current_user.id if current_user else None,
    )


# ----------------------------------------------------------------------
# 5. BÚSQUEDA DE EMERGENCIAS
# ----------------------------------------------------------------------
@router.get(
    "/emergencies",
    response_model=PaginatedEmergenciesSearch,
    status_code=status.HTTP_200_OK,
    summary="Búsqueda y monitoreo geolocalizado de emergencias activas",
)
async def search_emergencies(
    q: Optional[str] = Query(None, description="Tipo o descripción de emergencia (ej: fuga de gas, incendio, robo)"),
    latitude: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Latitud del usuario"),
    longitude: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Longitud del usuario"),
    radius_km: Optional[float] = Query(None, description="Radio máximo en km"),
    severity: Optional[str] = Query(None, description="critical, high, medium, low"),
    community_id: Optional[uuid.UUID] = Query(None, description="Filtrar por comunidad"),
    sort: SearchSort = Query(SearchSort.RECOMMENDED, description="relevance, distance, recommended"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Optional[CurrentUser] = Depends(get_optional_current_user),
    service: SearchService = Depends(get_search_service),
):
    """
    Retorna alertas de emergencias barriales.
    Prioriza estrictamente gravedad (severidad crítica/alta), cercanía y estado activo.
    Nunca califica ni ordena emergencias por reputación.
    """
    return await service.search_emergencies(
        query=q,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        severity=severity,
        community_id=community_id,
        sort=sort,
        page=page,
        page_size=page_size,
        user_id=current_user.id if current_user else None,
    )


# ----------------------------------------------------------------------
# 6. RECOMENDACIONES PERSISTIDAS (AI RECOMMENDATIONS)
# ----------------------------------------------------------------------
@router.get(
    "/recommendations",
    summary="Consultar recomendaciones activas del usuario persistidas por IA",
)
async def get_persisted_recommendations(
    rec_type: Optional[str] = Query(None, description="Filtrar por tipo: service, product, solidarity, emergency"),
    limit: int = Query(10, ge=1, le=50),
    current_user: CurrentUser = Depends(get_current_user),
    service: SearchService = Depends(get_search_service),
):
    """Retorna las recomendaciones activas calculadas por el motor de IA para el usuario."""
    return await service.get_user_recommendations(
        user_id=current_user.id,
        rec_type=rec_type,
        limit=limit,
    )

