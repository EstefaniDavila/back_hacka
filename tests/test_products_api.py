import uuid
from decimal import Decimal
import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock

from app.main import app
from app.modules.commerce.dependencies import get_commerce_service
from app.modules.commerce.schemas import (
    ProductCategoryResponse,
    ProductListItemResponse,
)
from app.shared.pagination import PageMeta, PaginatedResponse


@pytest.mark.asyncio
async def test_list_product_categories():
    """Prueba listado de categorías de productos."""
    mock_cats = [
        ProductCategoryResponse(id=uuid.uuid4(), name="Panadería y Pastelería"),
        ProductCategoryResponse(id=uuid.uuid4(), name="Comida Casera"),
    ]

    mock_service = AsyncMock()
    mock_service.list_product_categories.return_value = mock_cats

    app.dependency_overrides[get_commerce_service] = lambda: mock_service
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            res = await client.get("/api/v1/products/categories")
            assert res.status_code == 200
            data = res.json()
            assert len(data) == 2
            assert data[0]["name"] == "Panadería y Pastelería"
    finally:
        app.dependency_overrides.pop(get_commerce_service, None)


@pytest.mark.asyncio
async def test_list_products():
    """Prueba listado paginado de productos locales."""
    mock_prod = ProductListItemResponse(
        id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        seller_name="Doña Rosa",
        category_name="Panadería",
        name="Pan casero artesanal",
        description="Recién horneado",
        price=Decimal("0.50"),
        stock=45,
        status="active",
        rating=4.9,
        reviews_count=28,
        distance_m=180,
    )
    mock_response = PaginatedResponse(
        items=[mock_prod],
        meta=PageMeta(total=1, page=1, limit=20, total_pages=1),
    )

    mock_service = AsyncMock()
    mock_service.list_products.return_value = mock_response

    app.dependency_overrides[get_commerce_service] = lambda: mock_service
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            res = await client.get("/api/v1/products")
            assert res.status_code == 200
            data = res.json()
            assert len(data["items"]) == 1
            assert data["items"][0]["name"] == "Pan casero artesanal"
            assert float(data["items"][0]["price"]) == 0.50
    finally:
        app.dependency_overrides.pop(get_commerce_service, None)
