import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock

from app.main import app
from app.modules.solidarity.dependencies import get_solidarity_service
from app.modules.solidarity.schemas import (
    SolidarityPostDetail,
    SolidarityPostListItem,
)
from app.shared.pagination import PageMeta, PaginatedResponse


@pytest.mark.asyncio
async def test_list_solidarity_posts():
    """Prueba que el endpoint de muro solidario retorne formato paginado correcto."""
    mock_post = SolidarityPostListItem(
        id=uuid.uuid4(),
        author_id=uuid.uuid4(),
        author_name="María Quispe",
        author_avatar=None,
        community_id=uuid.uuid4(),
        community_name="Zona A",
        category="Herramientas",
        post_type="request",
        title="Necesito una escalera",
        description="Para un trabajo en casa",
        status="active",
        responses_count=2,
    )
    mock_response = PaginatedResponse(
        items=[mock_post],
        meta=PageMeta(total=1, page=1, limit=20, total_pages=1),
    )

    mock_service = AsyncMock()
    mock_service.list_posts.return_value = mock_response

    app.dependency_overrides[get_solidarity_service] = lambda: mock_service
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            res = await client.get("/api/v1/solidarity/posts")
            assert res.status_code == 200
            data = res.json()
            assert "items" in data
            assert len(data["items"]) == 1
            assert data["items"][0]["title"] == "Necesito una escalera"
            assert data["items"][0]["post_type"] == "request"
    finally:
        app.dependency_overrides.pop(get_solidarity_service, None)


@pytest.mark.asyncio
async def test_create_solidarity_post_auth():
    """Prueba creación de publicación con autenticación."""
    user_id = uuid.uuid4()
    mock_detail = SolidarityPostDetail(
        id=uuid.uuid4(),
        author_id=user_id,
        author_name="Vecino Test",
        community_id=uuid.uuid4(),
        community_name="Zona A",
        category="Donaciones",
        post_type="offer",
        title="Donación de víveres",
        description="Alimentos no perecibles",
        status="active",
        responses_count=0,
    )

    mock_service = AsyncMock()
    mock_service.create_post.return_value = mock_detail

    app.dependency_overrides[get_solidarity_service] = lambda: mock_service
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            payload = {
                "title": "Donación de víveres",
                "description": "Alimentos no perecibles",
                "category": "Donaciones",
                "post_type": "offer",
            }
            res = await client.post(
                "/api/v1/solidarity/posts",
                json=payload,
                headers={"X-Test-User-Id": str(user_id)},
            )
            assert res.status_code == 201
            data = res.json()
            assert data["title"] == "Donación de víveres"
            assert data["status"] == "active"
    finally:
        app.dependency_overrides.pop(get_solidarity_service, None)
