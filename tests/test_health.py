import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_health_check_endpoint():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/health")
        assert response.status_code in (200, 503)
        data = response.json()
        assert "status" in data
        assert "app" in data
        assert "services" in data
        assert "database" in data["services"]
        assert data["app"]["name"] == "VeciRed IA Backend"


@pytest.mark.asyncio
async def test_root_endpoint():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "docs" in data
        assert "health" in data
