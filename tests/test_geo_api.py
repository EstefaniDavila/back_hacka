import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_get_departments_endpoint():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/geo/departments")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "meta" in data
        assert "total" in data["meta"]
        assert "page" in data["meta"]


@pytest.mark.asyncio
async def test_get_department_not_found():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/geo/departments/999999")
        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
        assert data["code"] == "ENTITY_NOT_FOUND"


@pytest.mark.asyncio
async def test_create_department_validation_error():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # name menor a 2 caracteres y ubigeo inválido
        response = await client.post(
            "/api/v1/geo/departments",
            json={"name": "A", "ubigeo": "1234"},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_communities_endpoint():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/geo/communities")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
