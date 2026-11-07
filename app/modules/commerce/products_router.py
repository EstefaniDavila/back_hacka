"""Rutas de API v1 para el catálogo de productos locales y comercio barrial de VeciRed IA."""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status

from app.core.security import CurrentUser, get_current_user
from app.modules.commerce.dependencies import get_commerce_service
from app.modules.commerce.schemas import (
    ProductCategoryResponse,
    ProductCreate,
    ProductDetailResponse,
    ProductListItemResponse,
    ProductStatusUpdate,
    ProductUpdate,
)
from app.modules.commerce.service import CommerceService
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/products", tags=["Productos y Comercio Barrial"])


# -------------------------------------------------------------
# CATEGORÍAS DE PRODUCTOS
# -------------------------------------------------------------
@router.get(
    "/categories",
    response_model=List[ProductCategoryResponse],
    summary="Listar categorías de productos",
)
async def list_product_categories(
    service: CommerceService = Depends(get_commerce_service),
):
    """Retorna las categorías disponibles para clasificar productos barriales (Panadería, Bodega, etc.)."""
    return await service.list_product_categories()


# -------------------------------------------------------------
# PRODUCTOS: EXPLORACIÓN Y BÚSQUEDA
# -------------------------------------------------------------
@router.get(
    "",
    response_model=PaginatedResponse[ProductListItemResponse],
    summary="Explorar productos locales disponibles con filtros",
)
async def list_products(
    q: Optional[str] = Query(None, description="Búsqueda por nombre de producto o descripción"),
    category_id: Optional[uuid.UUID] = Query(None, description="Filtrar por categoría"),
    business_id: Optional[uuid.UUID] = Query(None, description="Filtrar por negocio/bodega"),
    seller_id: Optional[uuid.UUID] = Query(None, description="Filtrar por vecino vendedor"),
    status: Optional[str] = Query("active", description="Estado del producto (active, out_of_stock, etc.)"),
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(20, ge=1, le=100, description="Cantidad por página"),
    service: CommerceService = Depends(get_commerce_service),
):
    """Retorna los productos activos del comercio barrial con paginación y filtros."""
    return await service.list_products(
        query=q,
        category_id=category_id,
        business_id=business_id,
        seller_id=seller_id,
        status=status,
        page=page,
        limit=limit,
    )


@router.get(
    "/my",
    response_model=PaginatedResponse[ProductListItemResponse],
    summary="Listar mis productos publicados",
)
async def list_my_products(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    service: CommerceService = Depends(get_commerce_service),
):
    """Retorna los productos publicados por el usuario actual."""
    return await service.list_products(
        seller_id=current_user.id,
        status=None,
        page=page,
        limit=limit,
    )


@router.get(
    "/{product_id}",
    response_model=ProductDetailResponse,
    summary="Consultar detalle de un producto",
)
async def get_product_detail(
    product_id: uuid.UUID,
    service: CommerceService = Depends(get_commerce_service),
):
    """Obtiene la información técnica y de contacto para un producto barrial."""
    return await service.get_product_detail(product_id)


# -------------------------------------------------------------
# PUBLICACIÓN, EDICIÓN Y GESTIÓN DE PRODUCTOS
# -------------------------------------------------------------
@router.post(
    "",
    response_model=ProductDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Publicar un nuevo producto local",
)
async def create_product(
    data: ProductCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: CommerceService = Depends(get_commerce_service),
):
    """Permite al vecino publicar un producto para su venta comunitaria."""
    return await service.create_product(
        user_id=current_user.id,
        data=data,
    )


@router.put(
    "/{product_id}",
    response_model=ProductDetailResponse,
    summary="Editar un producto propio",
)
async def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: CommerceService = Depends(get_commerce_service),
):
    """Permite modificar el nombre, descripción, precio, stock o imagen de un producto."""
    return await service.update_product(
        product_id=product_id,
        user_id=current_user.id,
        data=data,
    )


@router.patch(
    "/{product_id}/status",
    response_model=ProductDetailResponse,
    summary="Cambiar estado del producto (ej: out_of_stock, paused)",
)
async def update_product_status(
    product_id: uuid.UUID,
    status_update: ProductStatusUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: CommerceService = Depends(get_commerce_service),
):
    """Actualiza la disponibilidad del producto (ej: agotado o pausado temporalmente)."""
    return await service.update_product_status(
        product_id=product_id,
        user_id=current_user.id,
        status_update=status_update,
    )


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un producto propio",
)
async def delete_product(
    product_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: CommerceService = Depends(get_commerce_service),
):
    """Elimina definitivamente el producto del catálogo."""
    await service.delete_product(
        product_id=product_id,
        user_id=current_user.id,
    )
