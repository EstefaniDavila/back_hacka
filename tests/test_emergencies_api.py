import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock

from app.main import app
from app.modules.emergencies.dependencies import get_emergency_service
from app.modules.emergencies.schemas import (
    EmergencyListItemResponse,
)


@pytest.mark.asyncio
async def test_get_active_emergency():
    """Prueba que el endpoint de alerta activa devuelva la información del banner."""
    emg_id = uuid.uuid4()
    mock_emg = EmergencyListItemResponse(
        id=emg_id,
        reported_by=uuid.uuid4(),
        reporter_name="Comité Vecinal",
        community_id=uuid.uuid4(),
        community_name="Zona A",
        emergency_type="inundacion",
        title="Inundación en Zona A - Manzana 2",
        description="Ingreso de agua por desborde",
        severity="high",
        status="en_atencion",
        volunteers_count=4,
        radius_m=500,
    )

    mock_service = AsyncMock()
    mock_service.get_active_emergency.return_value = mock_emg

    app.dependency_overrides[get_emergency_service] = lambda: mock_service
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            res = await client.get("/api/v1/emergencies/active")
            assert res.status_code == 200
            data = res.json()
            assert data["id"] == str(emg_id)
            assert data["emergency_type"] == "inundacion"
            assert data["severity"] == "high"
    finally:
        app.dependency_overrides.pop(get_emergency_service, None)


@pytest.mark.asyncio
async def test_volunteer_registration():
    """Prueba registro de un voluntario para asistir en una emergencia."""
    user_id = uuid.uuid4()
    emg_id = uuid.uuid4()

    mock_resp = {
        "status": "success",
        "message": "Te has registrado como voluntario en camino para esta emergencia.",
        "emergency_id": str(emg_id),
        "volunteer_id": str(user_id),
    }

    mock_service = AsyncMock()
    mock_service.register_volunteer.return_value = mock_resp

    app.dependency_overrides[get_emergency_service] = lambda: mock_service
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            res = await client.post(
                f"/api/v1/emergencies/{emg_id}/volunteer",
                json={"message": "En camino con linternas y palas"},
                headers={"X-Test-User-Id": str(user_id)},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "success"
    finally:
        app.dependency_overrides.pop(get_emergency_service, None)
